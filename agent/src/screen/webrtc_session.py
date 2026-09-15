"""One WebRTC peer connection for one live-screen viewing session. The admin
browser always creates the offer; this just answers it and starts pushing
the screen-share track. Public STUN (no TURN) is enough for NAT traversal
when both sides can reach it directly — matches the "efficient realtime
mechanism" requirement without needing a media relay server."""

import logging

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from screen.capture_track import ScreenShareTrack

logger = logging.getLogger("sentineldesk.agent")

ICE_SERVERS = [RTCIceServer(urls=["stun:stun.l.google.com:19302"])]


class WebRTCSession:
    def __init__(self, fps: int = 12, max_width: int = 1280):
        self.pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=ICE_SERVERS))
        self.track = ScreenShareTrack(fps=fps, max_width=max_width)
        self.pc.addTrack(self.track)

        @self.pc.on("connectionstatechange")
        async def on_state_change():
            logger.info("WebRTC connection state: %s", self.pc.connectionState)

    async def handle_offer(self, sdp: str) -> str:
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        return self.pc.localDescription.sdp

    async def close(self):
        self.track.stop()
        await self.pc.close()
