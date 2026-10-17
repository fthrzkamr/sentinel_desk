from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

DASHBOARD_GROUP = "dashboard"


def broadcast_dashboard_event(event_type: str, payload: dict):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        DASHBOARD_GROUP,
        {"type": "dashboard.event", "event_type": event_type, "payload": payload},
    )
