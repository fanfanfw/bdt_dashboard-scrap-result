import logging
import asyncpg
import os
import re
import pandas as pd
import json
from datetime import datetime
from dotenv import load_dotenv
from fastapi import HTTPException  # Anda bisa ganti ini jika mau pakai Exception biasa

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Konfigurasi database remote VPS dan database lokal Django
DB_CARLISTMY = os.getenv("DB_CARLISTMY", "db_scrap_new")
DB_CARLISTMY_USERNAME = os.getenv("DB_CARLISTMY_USERNAME", "fanfan")
DB_CARLISTMY_PASSWORD = os.getenv("DB_CARLISTMY_PASSWORD", "cenanun")
DB_CARLISTMY_HOST = os.getenv("DB_CARLISTMY_HOST", "127.0.0.1")

DB_MUDAHMY = os.getenv("DB_MUDAHMY", "db_scrap_new")
DB_MUDAHMY_USERNAME = os.getenv("DB_MUDAHMY_USERNAME", "fanfan")
DB_MUDAHMY_PASSWORD = os.getenv("DB_MUDAHMY_PASSWORD", "cenanun")
DB_MUDAHMY_HOST = os.getenv("DB_MUDAHMY_HOST", "127.0.0.1")

# Nama tabel lokal Django (sesuaikan dengan migration Anda)
TB_CARLISTMY = os.getenv("TB_CARLISTMY", "dashboard_carscarlistmy")
TB_MUDAHMY = os.getenv("TB_MUDAHMY", "dashboard_carsmudahmy")
TB_PRICE_HISTORY_CARLISTMY = os.getenv("TB_PRICE_HISTORY_CARLISTMY", "dashboard_pricehistorycarlistmy")
TB_PRICE_HISTORY_MUDAHMY = os.getenv("TB_PRICE_HISTORY_MUDAHMY", "dashboard_pricehistorymudahmy")

# Fungsi utilitas
def convert_price(price_str):
    if isinstance(price_str, int):
        return price_str
    if isinstance(price_str, str) and 'RM' in price_str:
        return int(price_str.replace('RM', '').replace(',', '').strip())
    return None

def convert_mileage(mileage_str):
    if isinstance(mileage_str, int):
        return mileage_str
    if isinstance(mileage_str, str):
        numbers = re.findall(r'\d+', mileage_str)
        if numbers:
            mileage_value = int(numbers[-1])
            if mileage_value >= 1000:
                return mileage_value
            else:
                return mileage_value * 1000
    return None

def parse_datetime(value):
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return None
    elif isinstance(value, datetime):
        return value
    return None

def parse_date(value):
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    elif hasattr(value, 'date'):
        return value.date()
    return None

def clean_and_standardize_variant(text):
    if not text or text.strip() == "-":
        return "NO VARIANT"
    return text  # Tidak ada pembersihan, kembalikan apa adanya

# Koneksi database remote VPS
async def get_remote_db_connection(db_name, db_user, db_host, db_password):
    return await asyncpg.connect(
        user=db_user,
        password=db_password,
        database=db_name,
        host=db_host
    )

# Koneksi database lokal Django
async def get_local_db_connection():
    local_db = os.getenv("DB_NAME", "db_dashboard")
    local_user = os.getenv("DB_USER", "fanfan")
    local_password = os.getenv("DB_PASSWORD", "cenanun")
    local_host = os.getenv("DB_HOST", "localhost")
    local_port = os.getenv("DB_PORT", "5432")
    return await asyncpg.connect(
        user=local_user,
        password=local_password,
        database=local_db,
        host=local_host,
        port=local_port
    )

# Ambil data dari remote table
async def fetch_data_from_remote_db_carlistmy(conn):
    query = "SELECT * FROM public.cars_scrap_carlistmy"
    return await conn.fetch(query)

async def fetch_data_from_remote_db_mudahmy(conn):
    query = "SELECT * FROM public.cars_scrap_mudahmy"
    return await conn.fetch(query)

# Insert/update data ke lokal, dengan normalisasi cars_standard
async def insert_or_update_data_into_local_db(data, table_name, source):
    conn = await get_local_db_connection()
    skipped_records = []
    inserted_count = 0
    skipped_count = 0

    try:
        logger.info(f"🚀 Memulai proses insert/update untuk {source.upper()}...")
        for row in data:
            # Mapping field dari remote ke local (sesuaikan dengan struktur remote Anda)
            listing_url = row['listing_url']
            condition = row.get('condition')
            brand = row['brand'].upper() if row['brand'] else None
            model_group = clean_and_standardize_variant(row.get('model_group', ''))
            model = clean_and_standardize_variant(row['model'])
            variant = clean_and_standardize_variant(row['variant'])
            information_ads = row.get('informasi_iklan') or row.get('information_ads')
            location = row.get('lokasi') or row.get('location')
            price = row['price']
            year = row['year']
            mileage = row.get('mileage') or row.get('millage')
            transmission = row.get('transmission')
            seat_capacity = row.get('seat_capacity')
            engine_cc = row.get('engine_cc')
            fuel_type = row.get('fuel_type')
            images = row.get('gambar') or row.get('images')
            last_scraped_at = parse_datetime(row['last_scraped_at'])
            version = row.get('version', 1)
            created_at = parse_datetime(row['created_at'])
            sold_at = parse_datetime(row['sold_at'])
            status = row.get('status', 'active')
            last_status_check = parse_datetime(row.get('last_status_check'))
            information_ads_date = row.get('information_ads_date')
            # Hanya ambil ads_tag jika source adalah carlistmy
            ads_tag = row.get('ads_tag') if source == 'carlistmy' else None
            is_deleted = row.get('is_deleted', False)
            
            # Convert values
            price_int = convert_price(price)
            year_int = int(year) if year else None
            mileage_int = convert_mileage(mileage)

            # Skip jika information_ads = URGENT
            if information_ads == 'URGENT':
                skipped_count += 1
                skipped_records.append({
                    "source": source,
                    "listing_url": listing_url,
                    "brand": brand,
                    "model_group": model_group,
                    "model": model,
                    "variant": variant,
                    "price": price,
                    "year": year,
                    "mileage": mileage,
                    "reason": "URGENT listing"
                })
                continue

            # Validasi data wajib
            if not all([brand, model, variant, price_int, year_int]):
                skipped_count += 1
                skipped_records.append({
                    "source": source,
                    "listing_url": listing_url,
                    "brand": brand,
                    "model_group": model_group,
                    "model": model,
                    "variant": variant,
                    "price": price,
                    "year": year,
                    "mileage": mileage,
                    "reason": "Incomplete data"
                })
                continue

            # Handle images (convert string to list if needed)
            if isinstance(images, str):
                try:
                    images = json.loads(images)
                except Exception:
                    images = None
            if not isinstance(images, (list, type(None))):
                images = None

            # Convert images list to text for storage
            images_text = json.dumps(images) if images else None

            # Cari cars_standard_id berdasarkan brand, model_group, model, variant dengan logika bertingkat
            cars_standard_id = None
            if brand and model and variant:
                # Step 1: Cari berdasarkan brand_norm
                brand_matches = await conn.fetch("""
                    SELECT id, model_group_norm, model_group_raw, model_norm, model_raw, 
                           variant_norm, variant_raw, variant_raw2
                    FROM dashboard_carsstandard
                    WHERE UPPER(brand_norm) = $1
                """, brand)
                
                for candidate in brand_matches:
                    # Step 2: Cek model_group - prioritas model_group_norm dulu, lalu model_group_raw
                    model_group_match = False
                    if model_group:  # Jika ada model_group dari input
                        if candidate['model_group_norm'] and candidate['model_group_norm'].strip().upper() == model_group.strip().upper():
                            model_group_match = True
                        elif candidate['model_group_raw'] and candidate['model_group_raw'].strip().upper() == model_group.strip().upper():
                            model_group_match = True
                    else:  # Jika tidak ada model_group dari input, skip pengecekan model_group
                        model_group_match = True
                    
                    if not model_group_match:
                        continue
                    
                    # Step 3: Cek model - prioritas model_norm dulu, lalu model_raw
                    model_match = False
                    if candidate['model_norm'] and candidate['model_norm'].strip().upper() == model.strip().upper():
                        model_match = True
                    elif candidate['model_raw'] and candidate['model_raw'].strip().upper() == model.strip().upper():
                        model_match = True
                    
                    if not model_match:
                        continue
                    
                    # Step 4: Cek variant - prioritas variant_norm, lalu variant_raw, lalu variant_raw2
                    variant_match = False
                    if candidate['variant_norm'] and candidate['variant_norm'].strip().upper() == variant.strip().upper():
                        variant_match = True
                    elif candidate['variant_raw'] and candidate['variant_raw'].strip().upper() == variant.strip().upper():
                        variant_match = True
                    elif candidate['variant_raw2'] and candidate['variant_raw2'].strip().upper() == variant.strip().upper():
                        variant_match = True
                    
                    if variant_match:
                        cars_standard_id = candidate['id']
                        break  # Keluar dari loop jika sudah ditemukan match

            # Check if record exists based on listing_url
            existing_record = await conn.fetchrow(f"SELECT cars_standard_id FROM {table_name} WHERE listing_url = $1", listing_url)
            
            # Preserve existing cars_standard_id if new one is not found
            if existing_record and existing_record['cars_standard_id'] and not cars_standard_id:
                cars_standard_id = existing_record['cars_standard_id']

            # Buat query insert/update berdasarkan source
            if source == 'carlistmy':
                # Untuk carlistmy, include ads_tag
                await conn.execute(f"""
                    INSERT INTO {table_name} (
                        listing_url, condition, brand, model_group, model, variant, 
                        information_ads, location, price, year, mileage, transmission, 
                        seat_capacity, engine_cc, fuel_type, last_scraped_at, version, 
                        created_at, sold_at, status, images, last_status_check, 
                        information_ads_date, ads_tag, is_deleted, source, cars_standard_id
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, 
                        $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27
                    )
                    ON CONFLICT (listing_url) DO UPDATE SET
                        condition = EXCLUDED.condition,
                        brand = EXCLUDED.brand,
                        model_group = EXCLUDED.model_group,
                        model = EXCLUDED.model,
                        variant = EXCLUDED.variant,
                        information_ads = EXCLUDED.information_ads,
                        location = EXCLUDED.location,
                        price = EXCLUDED.price,
                        year = EXCLUDED.year,
                        mileage = EXCLUDED.mileage,
                        transmission = EXCLUDED.transmission,
                        seat_capacity = EXCLUDED.seat_capacity,
                        engine_cc = EXCLUDED.engine_cc,
                        fuel_type = EXCLUDED.fuel_type,
                        last_scraped_at = EXCLUDED.last_scraped_at,
                        version = EXCLUDED.version,
                        sold_at = EXCLUDED.sold_at,
                        status = EXCLUDED.status,
                        images = EXCLUDED.images,
                        last_status_check = EXCLUDED.last_status_check,
                        information_ads_date = EXCLUDED.information_ads_date,
                        ads_tag = EXCLUDED.ads_tag,
                        is_deleted = EXCLUDED.is_deleted,
                        source = EXCLUDED.source,
                        cars_standard_id = COALESCE(EXCLUDED.cars_standard_id, {table_name}.cars_standard_id)
                """,
                listing_url, condition, brand, model_group, model, variant, information_ads,
                location, price_int, year_int, mileage_int, transmission, seat_capacity,
                engine_cc, fuel_type, last_scraped_at, version, created_at, sold_at, 
                status, images_text, last_status_check, information_ads_date, ads_tag, 
                is_deleted, source, cars_standard_id)
            else:
                # Untuk mudahmy, exclude ads_tag
                await conn.execute(f"""
                    INSERT INTO {table_name} (
                        listing_url, condition, brand, model_group, model, variant, 
                        information_ads, location, price, year, mileage, transmission, 
                        seat_capacity, engine_cc, fuel_type, last_scraped_at, version, 
                        created_at, sold_at, status, images, last_status_check, 
                        information_ads_date, is_deleted, source, cars_standard_id
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, 
                        $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26
                    )
                    ON CONFLICT (listing_url) DO UPDATE SET
                        condition = EXCLUDED.condition,
                        brand = EXCLUDED.brand,
                        model_group = EXCLUDED.model_group,
                        model = EXCLUDED.model,
                        variant = EXCLUDED.variant,
                        information_ads = EXCLUDED.information_ads,
                        location = EXCLUDED.location,
                        price = EXCLUDED.price,
                        year = EXCLUDED.year,
                        mileage = EXCLUDED.mileage,
                        transmission = EXCLUDED.transmission,
                        seat_capacity = EXCLUDED.seat_capacity,
                        engine_cc = EXCLUDED.engine_cc,
                        fuel_type = EXCLUDED.fuel_type,
                        last_scraped_at = EXCLUDED.last_scraped_at,
                        version = EXCLUDED.version,
                        sold_at = EXCLUDED.sold_at,
                        status = EXCLUDED.status,
                        images = EXCLUDED.images,
                        last_status_check = EXCLUDED.last_status_check,
                        information_ads_date = EXCLUDED.information_ads_date,
                        is_deleted = EXCLUDED.is_deleted,
                        source = EXCLUDED.source,
                        cars_standard_id = COALESCE(EXCLUDED.cars_standard_id, {table_name}.cars_standard_id)
                """,
                listing_url, condition, brand, model_group, model, variant, information_ads,
                location, price_int, year_int, mileage_int, transmission, seat_capacity,
                engine_cc, fuel_type, last_scraped_at, version, created_at, sold_at, 
                status, images_text, last_status_check, information_ads_date, 
                is_deleted, source, cars_standard_id)

            inserted_count += 1

        # Simpan record yg dilewati
        if skipped_records:
            skipped_df = pd.DataFrame(skipped_records)
            skipped_df.to_csv(f"skipped_{source}.csv", index=False)
            logger.warning(f"⚠️ {len(skipped_records)} data dilewati, tersimpan di skipped_{source}.csv")

        return inserted_count, skipped_count
    finally:
        await conn.close()

# Sinkronisasi utama
async def sync_data_from_remote():
    logger.info("🚀 Memulai sinkronisasi dari remote database...")

    result_summary = {}

    # Sinkronisasi CarlistMY
    logger.info("[CarlistMY] Membuka koneksi remote...")
    remote_conn_carlistmy = await get_remote_db_connection(DB_CARLISTMY, DB_CARLISTMY_USERNAME, DB_CARLISTMY_HOST, DB_CARLISTMY_PASSWORD)
    logger.info("[CarlistMY] Terkoneksi.")
    
    data_carlistmy = await fetch_data_from_remote_db_carlistmy(remote_conn_carlistmy)
    logger.info(f"[CarlistMY] Data diambil: {len(data_carlistmy)}")

    inserted_carlistmy, skipped_carlistmy = await insert_or_update_data_into_local_db(data_carlistmy, TB_CARLISTMY, 'carlistmy')
    logger.info(f"[CarlistMY] Inserted: {inserted_carlistmy}, Skipped: {skipped_carlistmy}")

    # Sinkronisasi price_history CarlistMY
    data_price_history_carlistmy = await fetch_price_history_from_remote_db(remote_conn_carlistmy, 'carlistmy')
    await insert_or_update_price_history(data_price_history_carlistmy, TB_PRICE_HISTORY_CARLISTMY)
    logger.info("[CarlistMY] Sinkronisasi price_history selesai.")

    await remote_conn_carlistmy.close()

    result_summary['carlistmy'] = {
        'total_fetched': len(data_carlistmy),
        'inserted': inserted_carlistmy,
        'skipped': skipped_carlistmy
    }

    # Sinkronisasi MudahMY
    logger.info("[MudahMY] Membuka koneksi remote...")
    remote_conn_mudahmy = await get_remote_db_connection(DB_MUDAHMY, DB_MUDAHMY_USERNAME, DB_MUDAHMY_HOST, DB_MUDAHMY_PASSWORD)
    logger.info("[MudahMY] Terkoneksi.")
    
    data_mudahmy = await fetch_data_from_remote_db_mudahmy(remote_conn_mudahmy)
    logger.info(f"[MudahMY] Data diambil: {len(data_mudahmy)}")

    inserted_mudahmy, skipped_mudahmy = await insert_or_update_data_into_local_db(data_mudahmy, TB_MUDAHMY, 'mudahmy')
    logger.info(f"[MudahMY] Inserted: {inserted_mudahmy}, Skipped: {skipped_mudahmy}")

    # Sinkronisasi price_history MudahMY
    data_price_history_mudahmy = await fetch_price_history_from_remote_db(remote_conn_mudahmy, 'mudahmy')
    await insert_or_update_price_history(data_price_history_mudahmy, TB_PRICE_HISTORY_MUDAHMY)
    logger.info("[MudahMY] Sinkronisasi price_history selesai.")

    await remote_conn_mudahmy.close()

    result_summary['mudahmy'] = {
        'total_fetched': len(data_mudahmy),
        'inserted': inserted_mudahmy,
        'skipped': skipped_mudahmy
    }

    logger.info("✅ Sinkronisasi semua sumber selesai.")
    result_summary["status"] = "success"
    return result_summary

async def fetch_price_history_from_remote_db(conn, source):
    if source == 'carlistmy':
        query = "SELECT listing_url, old_price, new_price, changed_at FROM public.price_history_scrap_carlistmy"
    elif source == 'mudahmy':
        query = "SELECT listing_url, old_price, new_price, changed_at FROM public.price_history_scrap_mudahmy"
    else:
        raise HTTPException(status_code=400, detail="Invalid source for price history.")
    return await conn.fetch(query)

async def insert_or_update_price_history(data, table_name):
    conn = await get_local_db_connection()
    try:
        if table_name == TB_PRICE_HISTORY_CARLISTMY:
            cars_table = TB_CARLISTMY
        elif table_name == TB_PRICE_HISTORY_MUDAHMY:
            cars_table = TB_MUDAHMY
        else:
            raise Exception("Unknown table name for price history.")

        # Ambil semua listing_url mobil yang ada di lokal
        cars_rows = await conn.fetch(f"SELECT listing_url FROM {cars_table}")
        url_set = set(row['listing_url'] for row in cars_rows)

        inserted = 0
        skipped = 0
        for row in data:
            listing_url = row['listing_url']
            old_price = row['old_price']
            new_price = row['new_price']
            changed_at = row['changed_at']

            # Pastikan listing_url ada di tabel mobil
            if listing_url not in url_set:
                skipped += 1
                continue

            # Insert/update price history dengan listing_url sebagai foreign key
            await conn.execute(f"""
                INSERT INTO {table_name} (listing_url, old_price, new_price, changed_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (listing_url, changed_at)
                DO UPDATE SET 
                    old_price = EXCLUDED.old_price,
                    new_price = EXCLUDED.new_price
            """, listing_url, old_price, new_price, changed_at)
            inserted += 1

        logger.info(f"[{table_name}] Inserted {inserted} records, Skipped {skipped} records due to missing listing_url.")
    finally:
        await conn.close()