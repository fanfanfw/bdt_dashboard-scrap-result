from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='LocationStandard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('states', models.CharField(max_length=255)),
                ('district', models.CharField(max_length=255)),
                ('town', models.CharField(max_length=255)),
                ('latitude', models.DecimalField(decimal_places=6, help_text='Latitude coordinate in decimal degrees', max_digits=9)),
                ('longitude', models.DecimalField(decimal_places=6, help_text='Longitude coordinate in decimal degrees', max_digits=9)),
                ('location_raw1', models.CharField(blank=True, max_length=255, null=True)),
                ('location_raw2', models.CharField(blank=True, max_length=255, null=True)),
                ('location_raw3', models.CharField(blank=True, max_length=255, null=True)),
                ('location_raw4', models.CharField(blank=True, max_length=255, null=True)),
                ('location_raw5', models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
        # Note: CarsStandard, CarsUnified, and PriceHistoryUnified are unmanaged models
        # They reference existing tables in db_test database
        migrations.CreateModel(
            name='CarsStandard',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('brand_norm', models.CharField(max_length=100)),
                ('model_group_norm', models.CharField(max_length=100)),
                ('model_norm', models.CharField(max_length=100)),
                ('variant_norm', models.CharField(max_length=100)),
                ('model_group_raw', models.CharField(blank=True, max_length=100, null=True)),
                ('model_raw', models.CharField(blank=True, max_length=100, null=True)),
                ('variant_raw', models.CharField(blank=True, max_length=100, null=True)),
                ('variant_raw2', models.CharField(blank=True, max_length=100, null=True)),
            ],
            options={
                'managed': False,
                'db_table': 'cars_standard',
            },
        ),
        migrations.CreateModel(
            name='CarsUnified',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('cars_standard', models.ForeignKey('CarsStandard', on_delete=models.CASCADE, null=True, blank=True, db_column='cars_standard_id')),
                ('source', models.CharField(choices=[('carlistmy', 'Carlist.my'), ('mudahmy', 'Mudah.my')], max_length=20)),
                ('listing_url', models.TextField()),
                ('condition', models.CharField(blank=True, max_length=50, null=True)),
                ('brand', models.CharField(max_length=100)),
                ('model_group', models.CharField(blank=True, max_length=100, null=True)),
                ('model', models.CharField(max_length=100)),
                ('variant', models.CharField(blank=True, max_length=100, null=True)),
                ('year', models.IntegerField(blank=True, null=True)),
                ('mileage', models.IntegerField(blank=True, null=True)),
                ('transmission', models.CharField(blank=True, max_length=50, null=True)),
                ('seat_capacity', models.CharField(blank=True, max_length=10, null=True)),
                ('engine_cc', models.CharField(blank=True, max_length=50, null=True)),
                ('fuel_type', models.CharField(blank=True, max_length=50, null=True)),
                ('price', models.IntegerField(blank=True, null=True)),
                ('location', models.CharField(blank=True, max_length=255, null=True)),
                ('information_ads', models.TextField(blank=True, null=True)),
                ('images', models.TextField(blank=True, null=True)),
                ('status', models.CharField(default='active', max_length=20)),
                ('ads_tag', models.CharField(blank=True, max_length=50, null=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('last_scraped_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.IntegerField(default=1)),
                ('sold_at', models.DateTimeField(blank=True, null=True)),
                ('last_status_check', models.DateTimeField(blank=True, null=True)),
                ('information_ads_date', models.DateField(blank=True, null=True)),
            ],
            options={
                'managed': False,
                'db_table': 'cars_unified',
            },
        ),
        migrations.CreateModel(
            name='PriceHistoryUnified',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('source', models.CharField(choices=[('carlistmy', 'Carlist.my'), ('mudahmy', 'Mudah.my')], max_length=20)),
                ('old_price', models.IntegerField(blank=True, null=True)),
                ('new_price', models.IntegerField()),
                ('listing_url', models.TextField()),
                ('changed_at', models.DateTimeField()),
            ],
            options={
                'managed': False,
                'db_table': 'price_history_unified',
            },
        ),
    ]