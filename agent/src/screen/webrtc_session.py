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

# Upgrade aiortc's internal encoder bitrates and parameters for crisp desktop streaming
# (prevents blurry macroblocks, downsampled text, and low-res artifacts on desktop streaming)
try:
    import aiortc.codecs.h264 as h264_codec

    h264_codec.MIN_BITRATE = 2_000_000
    h264_codec.DEFAULT_BITRATE = 4_000_000
    h264_codec.MAX_BITRATE = 10_000_000
except Exception:
    pass

try:
    import aiortc.codecs.vpx as vpx_codec

    vpx_codec.MIN_BITRATE = 2_000_000
    vpx_codec.DEFAULT_BITRATE = 4_000_000
    vpx_codec.MAX_BITRATE = 10_000_000

    # Patch Vp8Encoder for crystal-clear desktop text:
    # 1. qmax=30 (instead of default 56) eliminates severe lossy compression & blur
    # 2. noise-sensitivity=0 disables webcam noise-filtering which blurs small UI fonts
    def _tuned_vp8_encode(self, frame, force_keyframe: bool = False):
        assert isinstance(frame, vpx_codec.VideoFrame)
        if frame.format.name != "yuv420p":
            frame = frame.reformat(format="yuv420p")

        if self.codec and (
            frame.width != self.codec.width
            or frame.height != self.codec.height
            or abs(self.target_bitrate - self.codec.bit_rate) / self.codec.bit_rate > 0.1
        ):
            self.codec = None

        if force_keyframe:
            frame.pict_type = vpx_codec.av.video.frame.PictureType.I

        if self.codec is None:
            self.codec = vpx_codec.av.CodecContext.create("libvpx", "w")
            self.codec.width = frame.width
            self.codec.height = frame.height
            self.codec.bit_rate = max(2_000_000, self.target_bitrate)
            self.codec.pix_fmt = "yuv420p"
            self.codec.gop_size = 1800
            self.codec.qmin = 2
            self.codec.qmax = 30
            self.codec.options = {
                "bufsize": str(max(2_000_000, self.target_bitrate)),
                "cpu-used": "-6",
                "deadline": "realtime",
                "lag-in-frames": "0",
                "minrate": str(max(2_000_000, self.target_bitrate)),
                "maxrate": str(max(4_000_000, self.target_bitrate)),
                "noise-sensitivity": "0",
                "overshoot-pct": "15",
                "partitions": "0",
                "static-thresh": "0",
                "undershoot-pct": "100",
            }
            self.codec.thread_count = vpx_codec.number_of_threads(
                frame.width * frame.height, vpx_codec.multiprocessing.cpu_count()
            )

        data_to_send = b""
        for package in self.codec.encode(frame):
            data_to_send += bytes(package)

        payloads = self._packetize(data_to_send, self.picture_id)
        timestamp = vpx_codec.convert_timebase(frame.pts, frame.time_base, vpx_codec.VIDEO_TIME_BASE)
        self.picture_id = (self.picture_id + 1) % (1 << 15)
        return payloads, timestamp

    vpx_codec.Vp8Encoder.encode = _tuned_vp8_encode
except Exception:
    pass

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
        fps: int = 15,
        max_width: int = 1920,
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

