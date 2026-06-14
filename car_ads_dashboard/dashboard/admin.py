from django.contrib import admin

from .models import CarsStandardMaintenanceJob


@admin.register(CarsStandardMaintenanceJob)
class CarsStandardMaintenanceJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'job_type', 'status', 'target_table', 'dry_run', 'requested_by', 'created_at', 'started_at', 'finished_at')
    list_filter = ('job_type', 'status', 'target_table', 'dry_run', 'created_at')
    search_fields = ('id', 'celery_task_id', 'target_table', 'requested_by__username')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'finished_at')
