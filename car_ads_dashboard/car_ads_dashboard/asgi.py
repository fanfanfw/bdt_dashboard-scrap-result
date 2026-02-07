"""
ASGI config for car_ads_dashboard project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.conf import settings
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import dashboard.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'car_ads_dashboard.settings')

django_asgi_app = get_asgi_application()

serve_static = os.getenv("DJANGO_SERVE_STATIC", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}
if settings.DEBUG or serve_static:
    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            dashboard.routing.websocket_urlpatterns
        )
    ),
})
