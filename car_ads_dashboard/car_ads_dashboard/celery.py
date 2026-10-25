import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'car_ads_dashboard.settings')

app = Celery('car_ads_dashboard')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Opt-in startup SIGTERM-handler report (source/test only, off by default).
if os.environ.get('CARS_TERM_DIAGNOSTIC') == '1':
    from .term_startup_hook import register

    register()
