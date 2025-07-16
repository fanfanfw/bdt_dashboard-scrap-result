from django.urls import re_path
from dashboard import consumers

websocket_urlpatterns = [
    re_path(r'ws/sync_notify/$', consumers.SyncNotificationConsumer.as_asgi()),
    re_path(r'ws/cronlogs/(?P<log_file_id>[^/]+)/$', consumers.CronLogConsumer.as_asgi()),
]
