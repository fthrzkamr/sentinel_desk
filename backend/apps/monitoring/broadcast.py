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


def broadcast_alert_triggered(alert):
    if alert is None:
        return
    broadcast_dashboard_event(
        "alert.triggered",
        {
            "id": alert.id,
            "device_id": alert.device.device_id,
            "category": alert.category,
            "severity": alert.severity,
            "message": alert.message,
        },
    )


def broadcast_alert_updated(alert):
    if alert is None:
        return
    broadcast_dashboard_event(
        "alert.updated",
        {
            "id": alert.id,
            "device_id": alert.device.device_id,
            "status": alert.status,
        },
    )
