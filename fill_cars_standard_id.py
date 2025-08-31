import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'car_ads_dashboard'))
from datetime import datetime
from dashboard import services
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)

async def find_cars_standard_id(conn, brand, model_group, model, variant):
    """
    Mencari cars_standard_id berdasarkan brand, model_group, model, variant
    dengan logika matching yang sama seperti di services.py
    """
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

    return cars_standard_id

async def fill_cars_standard_id_for_table(table_name, source):
    """
    Mengisi cars_standard_id yang NULL untuk tabel tertentu
    """
    conn = await services.get_local_db_connection()
    updated_count = 0
    failed_count = 0
    failed_records = []
    
    try:
        logger.info(f"🔍 Mencari record dengan cars_standard_id NULL di tabel {table_name}...")
        
        # Ambil semua record yang cars_standard_id nya NULL
        null_records = await conn.fetch(f"""
            SELECT listing_url, brand, model_group, model, variant
            FROM {table_name}
            WHERE cars_standard_id IS NULL
              AND brand IS NOT NULL 
              AND model IS NOT NULL 
              AND variant IS NOT NULL
        """)
        
        logger.info(f"📊 Ditemukan {len(null_records)} record dengan cars_standard_id NULL di {source}")
        
        if len(null_records) == 0:
            logger.info(f"✅ Tidak ada record yang perlu diupdate di {source}")
            return updated_count, failed_count, failed_records
        
        # Progress bar untuk pemrosesan record
        with tqdm(total=len(null_records), desc=f"🔄 {source}", 
                  unit="record", ncols=100, colour='green') as pbar:
            for record in null_records:
                listing_url = record['listing_url']
                brand = record['brand']
                model_group = record['model_group']
                model = record['model']
                variant = record['variant']
                
                # Cari cars_standard_id
                cars_standard_id = await find_cars_standard_id(conn, brand, model_group, model, variant)
                
                if cars_standard_id:
                    # Update cars_standard_id
                    await conn.execute(f"""
                        UPDATE {table_name}
                        SET cars_standard_id = $1
                        WHERE listing_url = $2
                    """, cars_standard_id, listing_url)
                    updated_count += 1
                    pbar.set_postfix({"✅ Updated": updated_count, "❌ Failed": failed_count})
                else:
                    failed_count += 1
                    failed_records.append({
                        'listing_url': listing_url,
                        'brand': brand,
                        'model_group': model_group,
                        'model': model,
                        'variant': variant,
                        'source': source
                    })
                    pbar.set_postfix({"✅ Updated": updated_count, "❌ Failed": failed_count})
                
                pbar.update(1)
                
        logger.info(f"✅ {source}: Selesai memproses {len(null_records)} record")
        logger.info(f"   📈 Berhasil update: {updated_count}")
        logger.info(f"   ❌ Gagal match: {failed_count}")
        
        return updated_count, failed_count, failed_records
        
    except Exception as e:
        logger.error(f"❌ Error saat memproses {source}: {str(e)}")
        raise
    finally:
        await conn.close()

async def fill_all_cars_standard_id():
    """
    Mengisi cars_standard_id untuk semua tabel (carlistmy dan mudahmy)
    """
    logger.info("🚀 Memulai proses pengisian cars_standard_id untuk record yang NULL...")
    
    start_time = datetime.now()
    total_updated = 0
    total_failed = 0
    all_failed_records = []
    
    try:
        # Process CarlistMY
        logger.info("=" * 60)
        logger.info("📋 Memproses tabel CarlistMY...")
        updated_carlistmy, failed_carlistmy, failed_records_carlistmy = await fill_cars_standard_id_for_table(
            services.TB_CARLISTMY, 'CarlistMY'
        )
        total_updated += updated_carlistmy
        total_failed += failed_carlistmy
        all_failed_records.extend(failed_records_carlistmy)
        
        # Process MudahMY
        logger.info("=" * 60)
        logger.info("📋 Memproses tabel MudahMY...")
        updated_mudahmy, failed_mudahmy, failed_records_mudahmy = await fill_cars_standard_id_for_table(
            services.TB_MUDAHMY, 'MudahMY'
        )
        total_updated += updated_mudahmy
        total_failed += failed_mudahmy
        all_failed_records.extend(failed_records_mudahmy)
        
        # Summary report
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("=" * 60)
        logger.info("📊 SUMMARY REPORT")
        logger.info("=" * 60)
        logger.info(f"⏱️  Waktu eksekusi: {duration}")
        logger.info(f"📈 Total record berhasil diupdate: {total_updated}")
        logger.info(f"❌ Total record gagal match: {total_failed}")
        logger.info("")
        logger.info("📋 Detail per tabel:")
        logger.info(f"   CarlistMY - Updated: {updated_carlistmy}, Failed: {failed_carlistmy}")
        logger.info(f"   MudahMY   - Updated: {updated_mudahmy}, Failed: {failed_mudahmy}")
        
        # Simpan record yang gagal ke CSV untuk analisis
        if all_failed_records:
            import pandas as pd
            failed_df = pd.DataFrame(all_failed_records)
            failed_filename = f"failed_cars_standard_id_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            failed_df.to_csv(failed_filename, index=False)
            logger.info(f"💾 Record yang gagal match disimpan di: {failed_filename}")
        
        logger.info("=" * 60)
        if total_updated > 0:
            logger.info("🎉 Proses pengisian cars_standard_id BERHASIL!")
        else:
            logger.info("ℹ️  Tidak ada record yang perlu diupdate")
        logger.info("=" * 60)
        
        return {
            'status': 'success',
            'total_updated': total_updated,
            'total_failed': total_failed,
            'duration': str(duration),
            'carlistmy': {'updated': updated_carlistmy, 'failed': failed_carlistmy},
            'mudahmy': {'updated': updated_mudahmy, 'failed': failed_mudahmy},
            'failed_records_file': failed_filename if all_failed_records else None
        }
        
    except Exception as e:
        logger.error(f"❌ Error dalam proses pengisian cars_standard_id: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'total_updated': total_updated,
            'total_failed': total_failed
        }

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    result = asyncio.run(fill_all_cars_standard_id())
    print("\n" + "=" * 60)
    print("HASIL AKHIR:")
    print("=" * 60)
    for key, value in result.items():
        print(f"{key}: {value}")