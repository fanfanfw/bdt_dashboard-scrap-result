from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import CarsStandardMaintenanceJob
from .services.cars_standard_maintenance import broadcast_cars_standard_job, execute_fill_standard_id, execute_insert_missing_cars_standard


def _set_job_running(job):
    job.status = CarsStandardMaintenanceJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.progress = {'current': 0, 'total': None, 'percent': 0, 'message': 'Job started'}
    job.save(update_fields=['status', 'started_at', 'progress', 'updated_at'])
    broadcast_cars_standard_job(job)


def _set_job_success(job, result):
    job.status = CarsStandardMaintenanceJob.STATUS_SUCCESS
    job.result = result
    job.progress = {'current': 1, 'total': 1, 'percent': 100, 'message': result.get('message', 'Job completed')}
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'result', 'progress', 'finished_at', 'updated_at'])
    broadcast_cars_standard_job(job)


def _set_job_failed(job, exc):
    job.status = CarsStandardMaintenanceJob.STATUS_FAILED
    job.error_message = str(exc)
    job.progress = {**(job.progress or {}), 'message': str(exc)}
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'error_message', 'progress', 'finished_at', 'updated_at'])
    broadcast_cars_standard_job(job)


def _progress_callback(job_id):
    def callback(progress):
        job = CarsStandardMaintenanceJob.objects.select_related('requested_by').get(pk=job_id)
        current = progress.get('current')
        total = progress.get('total')
        percent = progress.get('percent')
        if percent is None and total:
            percent = min(100, round(current * 100 / total))
        job.progress = {**progress, 'percent': percent}
        job.save(update_fields=['progress', 'updated_at'])
        broadcast_cars_standard_job(job)
    return callback


def _run_placeholder_job(job_id, expected_job_type):
    job = CarsStandardMaintenanceJob.objects.get(pk=job_id)
    try:
        with transaction.atomic():
            job = CarsStandardMaintenanceJob.objects.select_for_update().get(pk=job_id)
            if job.job_type != expected_job_type:
                raise ValueError('Job type does not match task wrapper')
            _set_job_running(job)
        result = {
            'message': 'Background job infrastructure is ready. Business logic is not implemented yet.',
            'job_type': expected_job_type,
            'dry_run': job.dry_run,
            'target_table': job.target_table,
            'sources': job.sources,
            'parameters': job.parameters,
        }
        _set_job_success(job, result)
        return result
    except Exception as exc:
        _set_job_failed(job, exc)
        raise


@shared_task(bind=True)
def insert_missing_cars_standard(self, job_id):
    job = CarsStandardMaintenanceJob.objects.select_related('requested_by').get(pk=job_id)
    try:
        with transaction.atomic():
            job = CarsStandardMaintenanceJob.objects.select_for_update().get(pk=job_id)
            if job.job_type != CarsStandardMaintenanceJob.JOB_INSERT_MISSING:
                raise ValueError('Job type does not match task wrapper')
            _set_job_running(job)
        result = execute_insert_missing_cars_standard(
            job.target_table,
            job.sources,
            job.requested_by,
            preview_token=job.parameters.get('preview_token'),
            dry_run=job.dry_run,
            progress_callback=_progress_callback(job_id),
        )
        _set_job_success(job, result)
        return result
    except Exception as exc:
        _set_job_failed(job, exc)
        raise


@shared_task(bind=True)
def fill_standard_id(self, job_id):
    job = CarsStandardMaintenanceJob.objects.select_related('requested_by').get(pk=job_id)
    try:
        with transaction.atomic():
            job = CarsStandardMaintenanceJob.objects.select_for_update().get(pk=job_id)
            if job.job_type != CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID:
                raise ValueError('Job type does not match task wrapper')
            _set_job_running(job)
        result = execute_fill_standard_id(
            job.target_table,
            job.sources,
            job.requested_by,
            batch_size=job.parameters.get('batch_size', 500),
            preview_token=job.parameters.get('preview_token'),
            dry_run=job.dry_run,
            progress_callback=_progress_callback(job_id),
        )
        _set_job_success(job, result)
        return result
    except Exception as exc:
        _set_job_failed(job, exc)
        raise
