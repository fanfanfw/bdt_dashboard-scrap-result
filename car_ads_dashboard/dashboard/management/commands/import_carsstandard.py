import os
import csv
from django.core.management.base import BaseCommand
from dashboard.models import CarsStandard  # ganti sesuai nama app kamu

class Command(BaseCommand):
    help = 'Import data CarsStandard dari CSV yang ada di folder dashboard/data/ dengan mengubah "NULL" menjadi None'

    def handle(self, *args, **kwargs):
        import os
        import csv
        from dashboard.models import CarsStandard

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_dir = os.path.dirname(base_dir)
        csv_path = os.path.join(app_dir, 'data', 'cars_standard.csv')

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f'File CSV tidak ditemukan di {csv_path}'))
            return

        def clean_value(value):
            if value is None:
                return None
            v = value.strip()
            if v.upper() == 'NULL' or v == '':
                return None
            return v

        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            count = 0
            for row in reader:
                CarsStandard.objects.create(
                    brand_norm=clean_value(row.get('brand_norm')),
                    model_group_norm=clean_value(row.get('model_group_norm')),
                    model_norm=clean_value(row.get('model_norm')),
                    variant_norm=clean_value(row.get('variant_norm')),
                    model_group_raw=clean_value(row.get('model_group_raw')),
                    model_raw=clean_value(row.get('model_raw')),
                    variant_raw=clean_value(row.get('variant_raw')),
                    variant_raw2=clean_value(row.get('variant_raw2')),
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} records from {csv_path}'))