# Generated migration for SyncStatus model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SyncStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_id', models.CharField(max_length=255, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('in_progress', 'In Progress'), ('success', 'Success'), ('failure', 'Failure')], default='pending', max_length=20)),
                ('message', models.TextField(blank=True, null=True)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('progress_percentage', models.IntegerField(default=0)),
                ('current_step', models.CharField(blank=True, max_length=255, null=True)),
                ('total_steps', models.IntegerField(default=1)),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
    ]
