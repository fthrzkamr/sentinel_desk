from django.urls import re_path

from .consumers import AdminSignalConsumer, AgentSignalConsumer

websocket_urlpatterns = [
    re_path(r"^ws/agent/(?P<device_id>[\w-]+)/signal/$", AgentSignalConsumer.as_asgi()),
    re_path(r"^ws/livescreen/(?P<device_id>[\w-]+)/$", AdminSignalConsumer.as_asgi()),
]
