import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken

from .broadcast import DASHBOARD_GROUP


@database_sync_to_async
def _get_authorized_user(token: str):
    from apps.accounts.models import User

    validated = AccessToken(token)
    user = User.objects.select_related("role").get(pk=validated["user_id"])
    if not user.is_active or not user.has_permission_code("monitoring.view"):
        return None
    return user


class DashboardConsumer(AsyncWebsocketConsumer):
    """Push channel for the admin dashboard: device online/offline, metric
    updates, alert notifications. Agents never connect here — they only ever
    talk to the REST endpoints authenticated with their own device token."""

    async def connect(self):
        query_string = parse_qs(self.scope["query_string"].decode())
        token = query_string.get("token", [None])[0]

        user = None
        if token:
            try:
                user = await _get_authorized_user(token)
            except Exception:  # noqa: BLE001 - any auth failure just rejects the socket
                user = None

        if not user:
            await self.close(code=4401)
            return

        self.scope["user"] = user
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)

    async def dashboard_event(self, event):
        await self.send(text_data=json.dumps({"type": event["event_type"], "payload": event["payload"]}))
