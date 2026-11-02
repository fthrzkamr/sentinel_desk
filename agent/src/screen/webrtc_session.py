"""One WebRTC peer connection for one live-screen viewing session. The admin
browser always creates the offer; this just answers it and starts pushing
the screen-share track. Public STUN (no TURN) is enough for NAT traversal
when both sides can reach it directly — matches the "efficient realtime
mechanism" requirement without needing a media relay server."""

import json
import logging

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from screen.capture_track import ScreenShareTrack
from screen.input_controller import InputController

logger = logging.getLogger("sentineldesk.agent")

DEFAULT_ICE_SERVERS = [RTCIceServer(urls=["stun:stun.l.google.com:19302"])]


def _build_ice_servers(configured_servers: list | None) -> list[RTCIceServer]:
    if not configured_servers:
        return DEFAULT_ICE_SERVERS
    servers = []
    for item in configured_servers:
        if isinstance(item, dict) and "urls" in item:
            urls = item["urls"] if isinstance(item["urls"], list) else [item["urls"]]
            servers.append(
                RTCIceServer(
                    urls=urls,
                    username=item.get("username"),
                    credential=item.get("credential"),
                )
            )
    return servers or DEFAULT_ICE_SERVERS


class WebRTCSession:
    def __init__(
        self,
        ice_servers: list | None = None,
        fps: int = 12,
        max_width: int = 1280,
        monitor_index: int = 1,
    ):
        servers = _build_ice_servers(ice_servers)
        self.pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=servers))
        self.track = ScreenShareTrack(fps=fps, max_width=max_width, monitor_index=monitor_index)
        self.pc.addTrack(self.track)
        self.input_controller = InputController()
        self.control_enabled = True
        self.control_channel = None

        @self.pc.on("connectionstatechange")
        async def on_state_change():
            logger.info("WebRTC connection state: %s", self.pc.connectionState)

        @self.pc.on("datachannel")
        def on_datachannel(channel):
            if channel.label == "control":
                self.control_channel = channel
                logger.info("WebRTC DataChannel 'control' established for remote input")

                @channel.on("message")
                def on_message(message):
                    self.handle_control_message(message)

    def set_monitor(self, monitor_index: int) -> None:
        self.track.set_monitor(monitor_index)

    def handle_control_message(self, raw_message) -> None:
        if not self.control_enabled:
            return
        try:
            if isinstance(raw_message, str):
                event = json.loads(raw_message)
            elif isinstance(raw_message, dict):
                event = raw_message
            else:
                return

            self.input_controller.handle_control_event(event, monitor_index=self.track.monitor_index)
        except Exception as exc:
            logger.debug("Failed to handle control message: %s", exc)

    async def handle_offer(self, sdp: str) -> str:
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        return self.pc.localDescription.sdp

    async def close(self):
        self.track.stop()
        await self.pc.close()

