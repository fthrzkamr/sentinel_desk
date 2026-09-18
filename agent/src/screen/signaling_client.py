"""Persistent WebSocket connection to the backend's live-screen signaling
endpoint. Runs in its own asyncio event loop on a background thread so it
never interferes with the agent's main sync metrics loop — a crash or reconnect
storm here can't take down heartbeat/metrics reporting."""

import asyncio
import json
import logging
import threading

import websockets

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
            logger.info("Admin requested to view this screen — waiting for connection offer")

        elif msg_type == "webrtc_offer":
            await self._end_session()
            self.session = WebRTCSession()
            answer_sdp = await self.session.handle_offer(message["sdp"])
            await ws.send(json.dumps({"type": "webrtc_answer", "sdp": answer_sdp}))
            logger.info("Live screen streaming started")

        elif msg_type in ("stop_live_screen", "agent_disconnected"):
            await self._end_session()

    async def _end_session(self):
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Live screen streaming stopped")
