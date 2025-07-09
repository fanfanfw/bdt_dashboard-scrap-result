import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'car_ads_dashboard'))
from datetime import datetime
from dashboard import services
import logging

logger = logging.getLogger(__name__)

async def fetch_data_from_remote_db_carlistmy_today(conn):
    today = datetime.now().strftime('%Y-%m-%d')
    query = f"SELECT * FROM public.cars_scrap_carlistmy WHERE information_ads_date = '{today}'"
    return await conn.fetch(query)

async def fetch_data_from_remote_db_mudahmy_today(conn):
    today = datetime.now().strftime('%Y-%m-%d')
    query = f"SELECT * FROM public.cars_scrap_mudahmy WHERE information_ads_date = '{today}'"
    return await conn.fetch(query)

async def fetch_recent_status_check_carlistmy_remote(conn):
    query = """
        SELECT * FROM public.cars_scrap_carlistmy
        WHERE last_status_check IS NOT NULL
          AND last_status_check >= (NOW() - INTERVAL '30 days')
        ORDER BY last_status_check;
    """
    return await conn.fetch(query)

async def fetch_recent_status_check_mudahmy_remote(conn):
    query = """
        SELECT * FROM public.cars_scrap_mudahmy
        WHERE last_status_check IS NOT NULL
          AND last_status_check >= (NOW() - INTERVAL '30 days')
        ORDER BY last_status_check;
    """
    return await conn.fetch(query)

async def sync_data_today():
    logger.info("🚀 Memulai sinkronisasi data terbaru (hari ini) dari remote database...")
    result_summary = {}

    # CarlistMY
    logger.info("[CarlistMY] Membuka koneksi remote...")
    remote_conn_carlistmy = await services.get_remote_db_connection(
        services.DB_CARLISTMY, services.DB_CARLISTMY_USERNAME, services.DB_CARLISTMY_HOST, services.DB_CARLISTMY_PASSWORD)
    logger.info("[CarlistMY] Terkoneksi.")
    data_carlistmy = await fetch_data_from_remote_db_carlistmy_today(remote_conn_carlistmy)
    logger.info(f"[CarlistMY] Data diambil: {len(data_carlistmy)}")
    inserted_carlistmy, skipped_carlistmy = await services.insert_or_update_data_into_local_db(
        data_carlistmy, services.TB_CARLISTMY, 'carlistmy')
    logger.info(f"[CarlistMY] Inserted: {inserted_carlistmy}, Skipped: {skipped_carlistmy}")

    # MudahMY
    logger.info("[MudahMY] Membuka koneksi remote...")
    remote_conn_mudahmy = await services.get_remote_db_connection(
        services.DB_MUDAHMY, services.DB_MUDAHMY_USERNAME, services.DB_MUDAHMY_HOST, services.DB_MUDAHMY_PASSWORD)
    logger.info("[MudahMY] Terkoneksi.")
    data_mudahmy = await fetch_data_from_remote_db_mudahmy_today(remote_conn_mudahmy)
    logger.info(f"[MudahMY] Data diambil: {len(data_mudahmy)}")
    inserted_mudahmy, skipped_mudahmy = await services.insert_or_update_data_into_local_db(
        data_mudahmy, services.TB_MUDAHMY, 'mudahmy')
    logger.info(f"[MudahMY] Inserted: {inserted_mudahmy}, Skipped: {skipped_mudahmy}")

    # Sinkronisasi data last_status_check 30 hari terakhir dari remote CarlistMY & MudahMY secara paralel
    logger.info("[SYNC] Sinkronisasi data last_status_check 30 hari terakhir dari remote (paralel)...")
    results = await asyncio.gather(
        fetch_recent_status_check_carlistmy_remote(remote_conn_carlistmy),
        fetch_recent_status_check_mudahmy_remote(remote_conn_mudahmy)
    )
    recent_carlistmy, recent_mudahmy = results

    logger.info(f"[CarlistMY] Data last_status_check 30 hari terakhir (remote): {len(recent_carlistmy)}")
    logger.info(f"[MudahMY] Data last_status_check 30 hari terakhir (remote): {len(recent_mudahmy)}")

    insert_results = await asyncio.gather(
        services.insert_or_update_data_into_local_db(recent_carlistmy, services.TB_CARLISTMY, 'carlistmy'),
        services.insert_or_update_data_into_local_db(recent_mudahmy, services.TB_MUDAHMY, 'mudahmy')
    )
    (inserted_recent_carlistmy, skipped_recent_carlistmy), (inserted_recent_mudahmy, skipped_recent_mudahmy) = insert_results

    logger.info(f"[CarlistMY] Inserted (recent): {inserted_recent_carlistmy}, Skipped (recent): {skipped_recent_carlistmy}")
    logger.info(f"[MudahMY] Inserted (recent): {inserted_recent_mudahmy}, Skipped (recent): {skipped_recent_mudahmy}")

    await remote_conn_carlistmy.close()
    await remote_conn_mudahmy.close()

    result_summary['carlistmy'] = {
        'total_fetched': len(data_carlistmy),
        'inserted': inserted_carlistmy,
        'skipped': skipped_carlistmy
    }
    result_summary['mudahmy'] = {
        'total_fetched': len(data_mudahmy),
        'inserted': inserted_mudahmy,
        'skipped': skipped_mudahmy
    }

    logger.info("✅ Sinkronisasi data terbaru selesai.")
    result_summary["status"] = "success"
    return result_summary

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    result = asyncio.run(sync_data_today())
    print(result)
