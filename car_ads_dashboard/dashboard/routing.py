from django.urls import re_path
from dashboard import consumers

websocket_urlpatterns = [
    re_path(r'ws/sync_notify/$', consumers.SyncNotificationConsumer.as_asgi()),
    re_path(r'ws/logs/(?P<session_id>[^/]+)/$', consumers.LogsConsumer.as_asgi()),
]
