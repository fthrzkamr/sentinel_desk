"""Persistent WebSocket connection to the backend's live-screen signaling
endpoint. Runs in its own asyncio event loop on a background thread so it
never interferes with the agent's main sync metrics loop — a crash or reconnect
storm here can't take down heartbeat/metrics reporting."""

import asyncio
import json
import logging
import threading

import websockets

from screen.capture_track import get_available_monitors
from screen.consent_dialog import ask_remote_permission
from screen.webrtc_session import WebRTCSession

logger = logging.getLogger("sentineldesk.agent")

MAX_BACKOFF_SECONDS = 60
PRESENCE_PING_INTERVAL_SECONDS = 20  # well under the backend's 60s presence TTL


class LiveScreenAgent:
    def __init__(self, server_url: str, device_id: str, device_token: str):
        ws_base = server_url.replace("https://", "wss://").replace("http://", "ws://")
        self.url = f"{ws_base}/ws/agent/{device_id}/signal/?token={device_token}"
        self.session: WebRTCSession | None = None
        self._stop_event = threading.Event()
        self._active_monitor_index = 1
        self._ice_servers = None
        self._permission_granted = False

    def start_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self._run_forever, daemon=True, name="livescreen-signaling")
        thread.start()
        return thread

    def stop(self):
        self._stop_event.set()

    def _run_forever(self):
        asyncio.run(self._main_loop())

    async def _main_loop(self):
        backoff = 1
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("Live-screen signaling connected")
                    backoff = 1
                    await self._handle_connection(ws)
            except Exception as exc:  # noqa: BLE001 - reconnect on literally any failure
                logger.info("Live-screen signaling disconnected (%s), retrying in %ss", exc, backoff)
                await self._end_session()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _handle_connection(self, ws):
        receive_task = asyncio.ensure_future(self._receive_loop(ws))
        ping_task = asyncio.ensure_future(self._ping_loop(ws))
        try:
            await receive_task
        finally:
            ping_task.cancel()

    async def _receive_loop(self, ws):
        async for raw_message in ws:
            try:
                message = json.loads(raw_message)
            except ValueError:
                continue
            await self._handle_message(ws, message)

    async def _ping_loop(self, ws):
        # The backend only refreshes this agent's "online" presence (used to decide
        # whether an admin may start a session) when it receives this app-level
        # ping — the WS protocol-level pong from `ping_interval` alone isn't enough.
        while True:
            await asyncio.sleep(PRESENCE_PING_INTERVAL_SECONDS)
            await ws.send(json.dumps({"type": "ping"}))

    async def _handle_message(self, ws, message: dict):
        msg_type = message.get("type")

        if msg_type == "viewer_joined":
            logger.info("Admin requested remote session — prompting client user for consent")
            if "ice_servers" in message:
                self._ice_servers = message.get("ice_servers")

            # Notify admin that consent dialog is active on client laptop
            await ws.send(
                json.dumps({
                    "type": "permission_pending",
                    "message": "Menunggu persetujuan pengguna laptop klien...",
                })
            )

            loop = asyncio.get_event_loop()
            granted = await loop.run_in_executor(None, ask_remote_permission, 30)

            if not granted:
                logger.info("Remote session rejected by client user or timed out")
                self._permission_granted = False
                await ws.send(
                    json.dumps({
                        "type": "permission_denied",
                        "message": "Permintaan remote ditolak oleh pengguna perangkat (atau waktu persetujuan habis).",
                    })
                )
                return

            logger.info("Remote session approved by client user")
            self._permission_granted = True
            await ws.send(json.dumps({"type": "permission_granted"}))

            try:
                monitors = get_available_monitors()
                await ws.send(
                    json.dumps({
                        "type": "monitors_list",
                        "monitors": monitors,
                        "active_monitor": self._active_monitor_index,
                    })
                )
            except Exception as exc:
                logger.warning("Could not query available monitors: %s", exc)

        elif msg_type == "webrtc_offer":
            if not getattr(self, "_permission_granted", False):
                logger.warning("webrtc_offer rejected: consent was not granted by client")
                await ws.send(
                    json.dumps({
                        "type": "permission_denied",
                        "message": "Permintaan remote belum atau tidak disetujui oleh pengguna.",
                    })
                )
                return
            await self._end_session()
            ice_servers = message.get("ice_servers") or self._ice_servers
            self.session = WebRTCSession(
                ice_servers=ice_servers,
                monitor_index=self._active_monitor_index,
            )
            answer_sdp = await self.session.handle_offer(message["sdp"])
            await ws.send(json.dumps({"type": "webrtc_answer", "sdp": answer_sdp}))
            logger.info("Live screen streaming started (monitor=%s)", self._active_monitor_index)

        elif msg_type == "switch_monitor":
            new_idx = int(message.get("monitor_index", 1))
            self._active_monitor_index = new_idx
            if self.session:
                self.session.set_monitor(new_idx)
            logger.info("Live screen switched capture to monitor %s", new_idx)
            await ws.send(json.dumps({"type": "monitor_switched", "active_monitor": new_idx}))

        elif msg_type == "remote_input":
            if self.session:
                self.session.handle_control_message(message.get("event", {}))

        elif msg_type in ("stop_live_screen", "agent_disconnected"):
            await self._end_session()

    async def _end_session(self):
        self._permission_granted = False
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Live screen streaming stopped")
