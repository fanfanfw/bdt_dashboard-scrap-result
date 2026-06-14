from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('dashboard', '0006_update_cars_dashboard_combined_view'),
    ]

    operations = [
        migrations.CreateModel(
            name='CarsStandardAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('update', 'Update'), ('merge', 'Merge')], max_length=20)),
                ('source_id', models.BigIntegerField(blank=True, null=True)),
                ('target_id', models.BigIntegerField(blank=True, null=True)),
                ('old_values', models.JSONField(blank=True, default=dict)),
                ('new_values', models.JSONField(blank=True, default=dict)),
                ('affected_references', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'dashboard_cars_standard_audit_log',
                'ordering': ['-created_at'],
            },
        ),
    ]
