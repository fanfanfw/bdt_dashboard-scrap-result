import os
import sys
import django
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

# Setup Django environment
sys.path.append('/home/fanff/fanfan/bdt_dashboard-scrap-result/car_ads_dashboard')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'car_ads_dashboard.settings')
django.setup()

# Import Django models after setup
from django.db import connection
from dashboard.models import CarsMudahmy, CarsCarlistmy, PriceHistoryMudahmy, PriceHistoryCarlistmy

load_dotenv(override=True)

class DjangoDataArchiver:
    def __init__(self):
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(f"data_archiver_{datetime.now().strftime('%Y%m%d')}.log"),
                logging.StreamHandler()
            ]
        )
    
    def create_archive_tables(self):
        """Membuat tabel arsip untuk semua tabel utama Django"""
        archive_tables = {
            'dashboard_carscarlistmy': 'dashboard_carscarlistmy_archive',
            'dashboard_carsmudahmy': 'dashboard_carsmudahmy_archive', 
            'dashboard_pricehistorycarlistmy': 'dashboard_pricehistorycarlistmy_archive',
            'dashboard_pricehistorymudahmy': 'dashboard_pricehistorymudahmy_archive'
        }
        
        with connection.cursor() as cursor:
            for original_table, archive_table in archive_tables.items():
                try:
                    # Membuat tabel arsip dengan struktur yang sama
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS {archive_table} 
                        (LIKE {original_table} INCLUDING ALL)
                    """)
                    
                    # Menambahkan kolom archived_at jika belum ada
                    cursor.execute(f"""
                        ALTER TABLE {archive_table} 
                        ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    """)
                    
                    logging.info(f"✅ Tabel arsip {archive_table} berhasil dibuat/diupdate")
                    
                except Exception as e:
                    logging.error(f"❌ Error membuat tabel arsip {archive_table}: {e}")
    
    def get_old_car_records(self, model_class, months=6):
        """Mengambil records mobil yang information_ads_date > months bulan"""
        cutoff_date = datetime.now().date() - timedelta(days=months * 30)
        
        return model_class.objects.filter(
            information_ads_date__lt=cutoff_date
        ).exclude(information_ads_date__isnull=True)
    
    def archive_cars_data(self, model_class, archive_table_name, months=6):
        """Archive data mobil menggunakan Django ORM"""
        try:
            # Ambil data lama yang akan diarsipkan
            old_records = self.get_old_car_records(model_class, months)
            
            if not old_records.exists():
                logging.info(f"ℹ️  Tidak ada data lama di tabel {model_class._meta.db_table}")
                return []
            
            # Ambil listing_urls untuk archiving price history
            listing_urls = list(old_records.values_list('listing_url', flat=True))
            
            # Insert ke archive menggunakan raw SQL untuk efficiency
            cutoff_date = datetime.now().date() - timedelta(days=months * 30)
            
            with connection.cursor() as cursor:
                try:
                    # INSERT...SELECT untuk efficiency
                    cursor.execute(f"""
                        INSERT INTO {archive_table_name} 
                        SELECT *, CURRENT_TIMESTAMP as archived_at
                        FROM {model_class._meta.db_table}
                        WHERE information_ads_date < %s 
                        AND information_ads_date IS NOT NULL
                    """, [cutoff_date])
                    
                    inserted_count = cursor.rowcount
                    
                    # Delete dari tabel asli
                    cursor.execute(f"""
                        DELETE FROM {model_class._meta.db_table}
                        WHERE information_ads_date < %s 
                        AND information_ads_date IS NOT NULL
                    """, [cutoff_date])
                    
                    deleted_count = cursor.rowcount
                    
                    # Commit transaction for this operation
                    connection.commit()
                    
                except Exception as e:
                    # Rollback pada error
                    connection.rollback()
                    raise e
            
            logging.info(f"✅ {inserted_count} record berhasil diarsipkan dari {model_class._meta.db_table}")
            logging.info(f"   - Inserted: {inserted_count}, Deleted: {deleted_count}")
            
            return listing_urls  # Return listing_urls for price history archiving
            
        except Exception as e:
            logging.error(f"❌ Error archiving {model_class._meta.db_table}: {e}")
            return []
    
    def archive_price_history_data(self, model_class, archive_table_name, listing_urls):
        """Archive data price history berdasarkan listing_urls yang sudah diarsipkan"""
        if not listing_urls:
            return
            
        try:
            with connection.cursor() as cursor:
                try:
                    # Cek dulu apakah ada data yang perlu diarsipkan
                    urls_placeholder = ', '.join(['%s'] * len(listing_urls))
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {model_class._meta.db_table} 
                        WHERE listing_url IN ({urls_placeholder})
                    """, listing_urls)
                    
                    price_count = cursor.fetchone()[0]
                    
                    if price_count == 0:
                        logging.info(f"ℹ️  Tidak ada data price history untuk listing_urls yang diarsipkan di tabel {model_class._meta.db_table}")
                        return
                    
                    # Insert ke tabel arsip menggunakan INSERT...SELECT
                    cursor.execute(f"""
                        INSERT INTO {archive_table_name} 
                        SELECT ph.*, CURRENT_TIMESTAMP as archived_at
                        FROM {model_class._meta.db_table} ph
                        WHERE ph.listing_url IN ({urls_placeholder})
                    """, listing_urls)
                    
                    inserted_count = cursor.rowcount
                    
                    # Hapus dari tabel asli
                    cursor.execute(f"""
                        DELETE FROM {model_class._meta.db_table} 
                        WHERE listing_url IN ({urls_placeholder})
                    """, listing_urls)
                    
                    deleted_count = cursor.rowcount
                    
                    # Commit transaction for this operation
                    connection.commit()
                    
                    logging.info(f"✅ {inserted_count} price history record berhasil diarsipkan dari {model_class._meta.db_table}")
                    logging.info(f"   - Inserted: {inserted_count}, Deleted: {deleted_count}")
                    
                except Exception as e:
                    # Rollback pada error
                    connection.rollback()
                    raise e
                
        except Exception as e:
            logging.error(f"❌ Error archiving price history {model_class._meta.db_table}: {e}")
    
    def run_archive_process(self, months=6):
        """Menjalankan proses archiving lengkap"""
        try:
            logging.info(f"🚀 Memulai proses archiving data yang lebih lama dari {months} bulan...")
            
            # Buat tabel arsip
            self.create_archive_tables()
            
            # Archive data carlistmy
            logging.info("📦 Archiving data carlistmy...")
            
            # Archive price history dulu sebelum cars (untuk menghindari foreign key constraint)
            cutoff_date = datetime.now().date() - timedelta(days=months * 30)
            
            # Get listing_urls yang akan diarsip untuk carlistmy
            carlistmy_urls = list(CarsCarlistmy.objects.filter(
                information_ads_date__lt=cutoff_date
            ).exclude(information_ads_date__isnull=True).values_list('listing_url', flat=True))
            
            if carlistmy_urls:
                logging.info("  📋 Archiving price history carlistmy terlebih dahulu...")
                self.archive_price_history_data(
                    PriceHistoryCarlistmy, 
                    'dashboard_pricehistorycarlistmy_archive', 
                    carlistmy_urls
                )
            
            # Archive cars carlistmy
            self.archive_cars_data(
                CarsCarlistmy, 
                'dashboard_carscarlistmy_archive', 
                months
            )
            
            # Archive data mudahmy
            logging.info("📦 Archiving data mudahmy...")
            
            # Get listing_urls yang akan diarsip untuk mudahmy
            mudahmy_urls = list(CarsMudahmy.objects.filter(
                information_ads_date__lt=cutoff_date
            ).exclude(information_ads_date__isnull=True).values_list('listing_url', flat=True))
            
            if mudahmy_urls:
                logging.info("  📋 Archiving price history mudahmy terlebih dahulu...")
                self.archive_price_history_data(
                    PriceHistoryMudahmy, 
                    'dashboard_pricehistorymudahmy_archive', 
                    mudahmy_urls
                )
            
            # Archive cars mudahmy
            self.archive_cars_data(
                CarsMudahmy,
                'dashboard_carsmudahmy_archive',
                months
            )
            
            logging.info("✅ Proses archiving selesai!")
            
        except Exception as e:
            logging.error(f"❌ Error dalam proses archiving: {e}")
            raise
    
    def dry_run_archive(self, months=6):
        """Simulasi archiving tanpa benar-benar memindahkan data"""
        try:
            logging.info(f"🔍 Simulasi archiving data yang lebih lama dari {months} bulan...")
            
            models_info = [
                (CarsCarlistmy, PriceHistoryCarlistmy, 'carlistmy'),
                (CarsMudahmy, PriceHistoryMudahmy, 'mudahmy')
            ]
            
            total_cars_to_archive = 0
            total_price_history_to_archive = 0
            
            for car_model, price_model, _ in models_info:
                # Hitung jumlah mobil yang akan diarsipkan
                old_cars = self.get_old_car_records(car_model, months)
                cars_count = old_cars.count()
                
                if cars_count > 0:
                    # Ambil listing_urls
                    listing_urls = list(old_cars.values_list('listing_url', flat=True))
                    
                    # Hitung jumlah price history yang akan diarsipkan
                    # Use the correct field name based on model's foreign key
                    if hasattr(price_model, 'car'):
                        # Django ORM menggunakan field 'car' yang mereference listing_url
                        price_count = price_model.objects.filter(car__in=listing_urls).count()
                    else:
                        price_count = price_model.objects.filter(listing_url__in=listing_urls).count()
                    
                    logging.info(f"  {car_model._meta.db_table}: {cars_count} records akan diarsipkan")
                    logging.info(f"  {price_model._meta.db_table}: {price_count} records akan diarsipkan")
                    
                    total_cars_to_archive += cars_count
                    total_price_history_to_archive += price_count
                else:
                    logging.info(f"  {car_model._meta.db_table}: Tidak ada data yang perlu diarsipkan")
            
            logging.info(f"\n📊 Total yang akan diarsipkan:")
            logging.info(f"  Total mobil: {total_cars_to_archive} records")
            logging.info(f"  Total price history: {total_price_history_to_archive} records")
            
        except Exception as e:
            logging.error(f"❌ Error dalam dry run: {e}")
    
    def get_archive_statistics(self):
        """Menampilkan statistik data arsip"""
        try:
            archive_tables = [
                'dashboard_carscarlistmy_archive',
                'dashboard_carsmudahmy_archive',
                'dashboard_pricehistorycarlistmy_archive', 
                'dashboard_pricehistorymudahmy_archive'
            ]
            
            logging.info("📊 Statistik data arsip:")
            
            with connection.cursor() as cursor:
                for table in archive_tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        
                        # Ambil tanggal arsip terbaru dan terlama
                        cursor.execute(f"""
                            SELECT MIN(archived_at), MAX(archived_at) 
                            FROM {table} 
                            WHERE archived_at IS NOT NULL
                        """)
                        date_range = cursor.fetchone()
                        
                        logging.info(f"  {table}: {count} records")
                        if date_range[0]:
                            logging.info(f"    Periode arsip: {date_range[0]} - {date_range[1]}")
                            
                    except Exception as e:
                        logging.warning(f"  {table}: Tabel belum ada atau error - {e}")
            
        except Exception as e:
            logging.error(f"❌ Error mendapatkan statistik: {e}")
    
    def get_current_data_statistics(self):
        """Menampilkan statistik data aktif saat ini"""
        try:
            logging.info("📊 Statistik data aktif:")
            
            models_info = [
                (CarsCarlistmy, PriceHistoryCarlistmy, 'carlistmy'),
                (CarsMudahmy, PriceHistoryMudahmy, 'mudahmy')
            ]
            
            for car_model, price_model, platform in models_info:
                cars_total = car_model.objects.count()
                cars_with_date = car_model.objects.exclude(information_ads_date__isnull=True).count()
                price_total = price_model.objects.count()
                
                # Data berdasarkan umur
                cutoff_6_months = datetime.now().date() - timedelta(days=6 * 30)
                cutoff_12_months = datetime.now().date() - timedelta(days=12 * 30)
                
                cars_old_6m = car_model.objects.filter(information_ads_date__lt=cutoff_6_months).count()
                cars_old_12m = car_model.objects.filter(information_ads_date__lt=cutoff_12_months).count()
                
                logging.info(f"  {platform.upper()}:")
                logging.info(f"    Cars total: {cars_total} records")
                logging.info(f"    Cars with date: {cars_with_date} records")
                logging.info(f"    Cars older than 6 months: {cars_old_6m} records")
                logging.info(f"    Cars older than 12 months: {cars_old_12m} records")
                logging.info(f"    Price history: {price_total} records")
                
        except Exception as e:
            logging.error(f"❌ Error mendapatkan statistik aktif: {e}")

def main():
    """Main function untuk menjalankan archiver"""
    import argparse
    
    # Setup command line arguments
    parser = argparse.ArgumentParser(description='Data Archiver untuk Car Ads Dashboard')
    parser.add_argument(
        '--months', '-m', 
        type=int, 
        default=6,
        help='Jumlah bulan untuk archiving data lama (default: 6 bulan)'
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true',
        help='Hanya jalankan simulasi tanpa melakukan archiving sesungguhnya'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true', 
        help='Hanya tampilkan statistik data tanpa melakukan archiving'
    )
    parser.add_argument(
        '--auto-confirm',
        action='store_true',
        help='Jalankan archiving tanpa konfirmasi manual (hati-hati!)'
    )
    
    args = parser.parse_args()
    
    # Validasi input
    if args.months < 1:
        print("❌ Error: Jumlah bulan harus minimal 1")
        return
    
    if args.months > 24:
        print("❌ Error: Jumlah bulan maksimal 24 (2 tahun)")
        return
    
    archiver = DjangoDataArchiver()
    
    print(f"🚀 Data Archiver - Archiving data yang lebih lama dari {args.months} bulan")
    print("=" * 60)
    
    # Tampilkan statistik sebelum archiving
    logging.info("📊 Statistik sebelum archiving:")
    archiver.get_current_data_statistics()
    archiver.get_archive_statistics()
    
    # Jika hanya ingin melihat statistik
    if args.stats_only:
        logging.info("ℹ️  Mode stats-only: Hanya menampilkan statistik.")
        return
    
    # Jalankan dry run terlebih dahulu
    logging.info(f"\n🔍 Dry run - simulasi archiving data > {args.months} bulan:")
    archiver.dry_run_archive(months=args.months)
    
    # Jika hanya dry run
    if args.dry_run:
        logging.info("ℹ️  Mode dry-run: Simulasi selesai tanpa melakukan archiving sesungguhnya.")
        return
    
    # Konfirmasi sebelum menjalankan archiving sesungguhnya
    if not args.auto_confirm:
        print("\n" + "="*60)
        print("⚠️  PERINGATAN: Proses archiving akan memindahkan data lama!")
        print("   Data yang dipindah tidak dapat dikembalikan dengan mudah.")
        print(f"   Data yang akan diarchive: lebih lama dari {args.months} bulan")
        print("="*60)
        
        confirm = input("Lanjutkan dengan archiving sesungguhnya? (yes/no): ").lower().strip()
    else:
        confirm = 'yes'
        logging.info("🤖 Mode auto-confirm: Melanjutkan archiving tanpa konfirmasi manual.")
    
    if confirm in ['yes', 'y']:
        # Jalankan proses archiving
        archiver.run_archive_process(months=args.months)
        
        # Tampilkan statistik setelah archiving
        logging.info("\n📊 Statistik setelah archiving:")
        archiver.get_current_data_statistics()
        archiver.get_archive_statistics()
    else:
        logging.info("❌ Archiving dibatalkan oleh user.")

if __name__ == "__main__":
    main()