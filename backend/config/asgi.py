import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_app = get_asgi_application()

from apps.livescreen.routing import websocket_urlpatterns as livescreen_ws_urlpatterns  # noqa: E402
from apps.monitoring.routing import websocket_urlpatterns as monitoring_ws_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(monitoring_ws_urlpatterns + livescreen_ws_urlpatterns),
    }
)
