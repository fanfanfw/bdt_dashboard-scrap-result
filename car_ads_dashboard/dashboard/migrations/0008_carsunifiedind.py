import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0007_carsstandardauditlog'),
    ]

    operations = [
        migrations.CreateModel(
            name='CarsUnifiedInd',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('source', models.CharField(max_length=50)),
                ('listing_id', models.TextField(blank=True, null=True)),
                ('listing_url', models.TextField(blank=True, null=True)),
                ('condition', models.CharField(blank=True, max_length=50, null=True)),
                ('brand', models.CharField(max_length=100)),
                ('model', models.CharField(max_length=100)),
                ('variant', models.CharField(blank=True, max_length=100, null=True)),
                ('series', models.CharField(blank=True, max_length=100, null=True)),
                ('type', models.CharField(blank=True, max_length=100, null=True)),
                ('year', models.IntegerField(blank=True, null=True)),
                ('mileage', models.IntegerField(blank=True, null=True)),
                ('transmission', models.CharField(blank=True, max_length=50, null=True)),
                ('seat_capacity', models.CharField(blank=True, max_length=10, null=True)),
                ('engine_cc', models.CharField(blank=True, max_length=50, null=True)),
                ('fuel_type', models.CharField(blank=True, max_length=50, null=True)),
                ('price', models.IntegerField(blank=True, null=True)),
                ('location', models.CharField(blank=True, max_length=255, null=True)),
                ('information_ads', models.TextField(blank=True, null=True)),
                ('images', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, null=True, size=None)),
                ('status', models.CharField(default='active', max_length=20)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('last_scraped_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.IntegerField(default=1)),
                ('information_ads_date', models.DateField(blank=True, null=True)),
                ('cars_standard', models.ForeignKey(blank=True, db_column='cars_standard_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='dashboard.carsstandard')),
            ],
            options={
                'db_table': 'cars_unified_ind',
                'managed': False,
            },
        ),
    ]
