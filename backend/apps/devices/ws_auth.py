from channels.db import database_sync_to_async


@database_sync_to_async
def get_device_from_token(device_id: str, raw_token: str):
    """Shared device-token-over-WebSocket auth for the agent signaling
    consumer. Mirrors DeviceTokenAuthentication's checks (unknown device,
    disabled device, wrong token all just mean "not authenticated")."""
    from .models import Device, DeviceCredential

    if not device_id or not raw_token:
        return None
    try:
        device = Device.objects.select_related("credential").get(device_id=device_id)
    except Device.DoesNotExist:
        return None
    if device.status == Device.Status.DISABLED:
        return None
    try:
        credential = device.credential
    except DeviceCredential.DoesNotExist:
        return None
    if not credential.check_token(raw_token):
        return None
    return device
