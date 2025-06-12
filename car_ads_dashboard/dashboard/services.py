import logging
import asyncpg
import os
import re
import pandas as pd
import json
from datetime import datetime
from dotenv import load_dotenv
from fastapi import HTTPException  # Anda bisa ganti ini jika mau pakai Exception biasa

load_dotenv()

logger = logging.getLogger(__name__)

# Konfigurasi database remote VPS dan database lokal Django
DB_CARLISTMY = os.getenv("DB_CARLISTMY", "scrap_carlistmy_old")
DB_CARLISTMY_USERNAME = os.getenv("DB_CARLISTMY_USERNAME", "fanfan")
DB_CARLISTMY_PASSWORD = os.getenv("DB_CARLISTMY_PASSWORD", "cenanun")
DB_CARLISTMY_HOST = os.getenv("DB_CARLISTMY_HOST", "127.0.0.1")

DB_MUDAHMY = os.getenv("DB_MUDAHMY", "scrap_mudahmy_old")
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
            return None
    elif isinstance(value, datetime):
        return value
    return None

def clean_and_standardize_variant(text):
    if not text or text.strip() == "-":
        return "NO VARIANT"
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().upper()

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
async def fetch_data_from_remote_db(conn):
    query = "SELECT * FROM public.cars"
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
            id_ = row['id']
            listing_url = row['listing_url']
            brand = row['brand'].upper() if row['brand'] else None
            model = clean_and_standardize_variant(row['model'])
            variant = clean_and_standardize_variant(row['variant'])
            informasi_iklan = row['informasi_iklan']
            lokasi = row['lokasi']
            price = row['price']
            year = row['year']
            mileage = row.get('mileage') or row.get('millage')
            transmission = row['transmission']
            seat_capacity = row['seat_capacity']
            gambar = row['gambar']
            last_scraped_at = parse_datetime(row['last_scraped_at'])
            version = row['version']
            created_at = parse_datetime(row['created_at'])
            sold_at = parse_datetime(row['sold_at'])
            status = row['status']
            last_status_check = parse_datetime(row['last_status_check'])
            price_int = convert_price(price)
            year_int = int(year) if year else None
            mileage_int = convert_mileage(mileage)

            # Skip jika informasi_iklan = URGENT
            if informasi_iklan == 'URGENT':
                skipped_count += 1
                skipped_records.append({
                    "source": source,
                    "id": id_,
                    "brand": brand,
                    "model": model,
                    "variant": variant,
                    "price": price,
                    "year": year,
                    "mileage": mileage,
                    "reason": "URGENT listing"
                })
                continue

            # Validasi data wajib
            if not all([brand, model, variant, price_int, mileage_int, year_int]):
                skipped_count += 1
                skipped_records.append({
                    "source": source,
                    "id": id_,
                    "brand": brand,
                    "model": model,
                    "variant": variant,
                    "price": price,
                    "year": year,
                    "mileage": mileage,
                    "reason": "Incomplete data"
                })
                continue

            if isinstance(gambar, str):
                try:
                    gambar = json.loads(gambar)
                except Exception:
                    gambar = []
            if not isinstance(gambar, list):
                gambar = []

            # Cari cars_standard_id sesuai brand, model, variant
            query_check = f"SELECT cars_standard_id FROM {table_name} WHERE id = $1"
            existing_standard_id = await conn.fetchval(query_check, id_)

            cars_standard_id = existing_standard_id
            if not existing_standard_id:
                norm_query = f"""
                    SELECT id FROM dashboard_carsstandard
                    WHERE UPPER(brand_norm) = $1
                      AND (UPPER(model_norm) = $2 OR UPPER(model_raw) = $2)
                      AND $3 IN (UPPER(variant_norm), UPPER(variant_raw), UPPER(variant_raw2))
                    LIMIT 1
                """
                norm_result = await conn.fetchrow(norm_query, brand, model, variant)
                if norm_result:
                    cars_standard_id = norm_result['id']

            # Insert/update data utama
            await conn.execute(f"""
                INSERT INTO {table_name} (
                    id, listing_url, brand, model, variant, informasi_iklan,
                    lokasi, price, year, mileage, transmission, seat_capacity,
                    gambar, last_scraped_at, version, created_at, sold_at, status, last_status_check,
                    cars_standard_id, source
                )
                VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                    $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21
                )
                ON CONFLICT (id) DO UPDATE SET
                    listing_url = EXCLUDED.listing_url,
                    brand = EXCLUDED.brand,
                    model = EXCLUDED.model,
                    variant = EXCLUDED.variant,
                    informasi_iklan = EXCLUDED.informasi_iklan,
                    lokasi = EXCLUDED.lokasi,
                    price = EXCLUDED.price,
                    year = EXCLUDED.year,
                    mileage = EXCLUDED.mileage,
                    transmission = EXCLUDED.transmission,
                    seat_capacity = EXCLUDED.seat_capacity,
                    gambar = EXCLUDED.gambar,
                    last_scraped_at = EXCLUDED.last_scraped_at,
                    version = EXCLUDED.version,
                    created_at = EXCLUDED.created_at,
                    sold_at = EXCLUDED.sold_at,
                    status = EXCLUDED.status,
                    last_status_check = EXCLUDED.last_status_check,
                    cars_standard_id = COALESCE(EXCLUDED.cars_standard_id, {table_name}.cars_standard_id),
                    source = EXCLUDED.source
            """,
            id_, listing_url, brand, model, variant, informasi_iklan,
            lokasi, price_int, year_int, mileage_int, transmission, seat_capacity,
            gambar, last_scraped_at, version, created_at, sold_at, status, last_status_check,
            cars_standard_id, source)

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
    
    data_carlistmy = await fetch_data_from_remote_db(remote_conn_carlistmy)
    logger.info(f"[CarlistMY] Data diambil: {len(data_carlistmy)}")

    inserted_carlistmy, skipped_carlistmy = await insert_or_update_data_into_local_db(data_carlistmy, TB_CARLISTMY, 'carlistmy')
    logger.info(f"[CarlistMY] Inserted: {inserted_carlistmy}, Skipped: {skipped_carlistmy}")

    # Sinkronisasi price_history CarlistMY
    data_price_history_carlistmy = await fetch_price_history_from_remote_db(remote_conn_carlistmy, 'carlistmy')
    await insert_or_update_price_history(data_price_history_carlistmy, TB_PRICE_HISTORY_CARLISTMY)
    logger.info("[CarlistMY] Sinkronisasi price_history selesai.")

    result_summary['carlistmy'] = {
        'total_fetched': len(data_carlistmy),
        'inserted': inserted_carlistmy,
        'skipped': skipped_carlistmy
    }

    # Sinkronisasi MudahMY
    logger.info("[MudahMY] Membuka koneksi remote...")
    remote_conn_mudahmy = await get_remote_db_connection(DB_MUDAHMY, DB_MUDAHMY_USERNAME, DB_MUDAHMY_HOST, DB_MUDAHMY_PASSWORD)
    logger.info("[MudahMY] Terkoneksi.")
    
    data_mudahmy = await fetch_data_from_remote_db(remote_conn_mudahmy)
    logger.info(f"[MudahMY] Data diambil: {len(data_mudahmy)}")

    inserted_mudahmy, skipped_mudahmy = await insert_or_update_data_into_local_db(data_mudahmy, TB_MUDAHMY, 'mudahmy')
    logger.info(f"[MudahMY] Inserted: {inserted_mudahmy}, Skipped: {skipped_mudahmy}")

    # Sinkronisasi price_history MudahMY
    data_price_history_mudahmy = await fetch_price_history_from_remote_db(remote_conn_mudahmy, 'mudahmy')
    await insert_or_update_price_history(data_price_history_mudahmy, TB_PRICE_HISTORY_MUDAHMY)
    logger.info("[MudahMY] Sinkronisasi price_history selesai.")

    result_summary['mudahmy'] = {
        'total_fetched': len(data_mudahmy),
        'inserted': inserted_mudahmy,
        'skipped': skipped_mudahmy
    }

    logger.info("✅ Sinkronisasi semua sumber selesai.")
    result_summary["status"] = "success"
    return result_summary

async def fetch_price_history_from_remote_db(conn, source):
    if source in ('carlistmy', 'mudahmy'):
        query = "SELECT car_id, old_price, new_price, changed_at FROM public.price_history_combined"
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

        existing_ids = await conn.fetch(f"SELECT id FROM {cars_table}")
        existing_ids_set = set(row['id'] for row in existing_ids)

        inserted = 0
        skipped = 0

        for row in data:
            car_id = row['car_id']
            old_price = row['old_price']
            new_price = row['new_price']
            changed_at = row['changed_at']

            if car_id not in existing_ids_set:
                skipped += 1
                continue

            await conn.execute(f"""
                INSERT INTO {table_name} (car_id, old_price, new_price, changed_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (car_id, changed_at) 
                DO UPDATE SET 
                    old_price = EXCLUDED.old_price,
                    new_price = EXCLUDED.new_price,
                    changed_at = EXCLUDED.changed_at
            """, car_id, old_price, new_price, changed_at)
            inserted += 1

        logger.info(f"[{table_name}] Inserted {inserted} records, Skipped {skipped} records due to missing cars.")

    finally:
        await conn.close()
