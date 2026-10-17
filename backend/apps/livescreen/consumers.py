import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.accounts.ws_auth import get_user_from_token, user_has_permission
from apps.audit.services import log_action
from apps.devices.ws_auth import get_device_from_token

from . import presence

alog = database_sync_to_async(log_action)


class AgentSignalConsumer(AsyncWebsocketConsumer):
    """The agent's end of the live-screen signaling channel. One persistent
    connection per device, authenticated with the same device token used for
    the REST endpoints. Never carries video itself — only WebRTC SDP/ICE
    signaling messages relayed to/from whichever admin is currently viewing."""

    async def connect(self):
        query = parse_qs(self.scope["query_string"].decode())
        device_id = self.scope["url_route"]["kwargs"]["device_id"]
        token = query.get("token", [None])[0]

        device = await get_device_from_token(device_id, token)
        if not device:
            await self.close(code=4401)
            return

        self.device_id = device_id
        await self.accept()
        presence.mark_agent_online(self.device_id, self.channel_name)

    async def disconnect(self, close_code):
        if not getattr(self, "device_id", None):
            return
        presence.mark_agent_offline(self.device_id)
        admin_channel = presence.get_admin_channel(self.device_id)
        if admin_channel:
            await self.channel_layer.send(
                admin_channel, {"type": "relay.message", "payload": {"type": "agent_disconnected"}}
            )

    async def receive(self, text_data):
        try:
            message = json.loads(text_data)
        except ValueError:
            return

        if message.get("type") == "ping":
            presence.refresh_agent_presence(self.device_id, self.channel_name)
            await self.send(text_data=json.dumps({"type": "pong"}))
            return

        admin_channel = presence.get_admin_channel(self.device_id)
        if admin_channel:
            await self.channel_layer.send(admin_channel, {"type": "relay.message", "payload": message})

    async def relay_message(self, event):
        await self.send(text_data=json.dumps(event["payload"]))


class AdminSignalConsumer(AsyncWebsocketConsumer):
    """The admin browser's end of the live-screen signaling channel. Requires
    `monitoring.live_screen` permission, a registered+enabled device, and an
    already-connected agent — and only one admin may view a given device at
    a time. Every start/stop is audit-logged."""

    async def connect(self):
        query = parse_qs(self.scope["query_string"].decode())
        self.device_id = self.scope["url_route"]["kwargs"]["device_id"]
        token = query.get("token", [None])[0]

        user = await get_user_from_token(token)
        if not user or not user_has_permission(user, "monitoring.live_screen"):
            await self.close(code=4403)
            return

        if not presence.is_agent_online(self.device_id):
            await self.accept()
            await self.send(text_data=json.dumps({"type": "error", "message": "Agent is not connected."}))
            await alog(user=user, action="livescreen.start_failed", device_id=self.device_id, metadata={"reason": "agent_offline"})
            await self.close(code=4404)
            return

        if presence.is_being_viewed(self.device_id):
            await self.accept()
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Device is already being viewed by another admin."})
            )
            await alog(user=user, action="livescreen.start_failed", device_id=self.device_id, metadata={"reason": "already_viewed"})
            await self.close(code=4409)
            return

        self.user = user
        await self.accept()
        presence.mark_admin_viewing(self.device_id, self.channel_name)
        await alog(user=user, action="livescreen.started", device_id=self.device_id, metadata={})

        agent_channel = presence.get_agent_channel(self.device_id)
        await self.channel_layer.send(agent_channel, {"type": "relay.message", "payload": {"type": "viewer_joined"}})

    async def disconnect(self, close_code):
        if not getattr(self, "user", None):
            return
        presence.clear_admin_viewing(self.device_id)
        await alog(user=self.user, action="livescreen.stopped", device_id=self.device_id, metadata={})

        agent_channel = presence.get_agent_channel(self.device_id)
        if agent_channel:
            await self.channel_layer.send(
                agent_channel, {"type": "relay.message", "payload": {"type": "stop_live_screen"}}
            )

    async def receive(self, text_data):
        try:
            message = json.loads(text_data)
        except ValueError:
            return

        agent_channel = presence.get_agent_channel(self.device_id)
        if not agent_channel:
            await self.send(text_data=json.dumps({"type": "error", "message": "Agent disconnected."}))
            return
        await self.channel_layer.send(agent_channel, {"type": "relay.message", "payload": message})

    async def relay_message(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
