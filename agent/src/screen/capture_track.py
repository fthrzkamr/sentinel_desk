"""Screen-share video track for aiortc. Captures the primary display via mss
at a capped resolution/FPS — this is the "bandwidth control" knob from the
spec: we deliberately don't stream full native resolution at 60fps."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import mss
import numpy as np
from aiortc import VideoStreamTrack
from av import VideoFrame
from PIL import Image

VIDEO_CLOCK_RATE = 90000
DEFAULT_FPS = 15
DEFAULT_MAX_WIDTH = 2560


def get_available_monitors() -> list[dict]:
    """Returns the list of available monitors detected on this device.
    mss: index 0 is virtual combined desktop (if multiple displays), index 1..N are physical monitors."""
    try:
        factory = getattr(mss, "MSS", mss.mss)
        with factory() as sct:
            monitors = []
            raw = sct.monitors
            if len(raw) > 2:
                monitors.append({
                    "index": 0,
                    "name": "Semua Monitor (Gabungan)",
                    "width": raw[0]["width"],
                    "height": raw[0]["height"],
                })
            for idx in range(1, len(raw)):
                m = raw[idx]
                monitors.append({
                    "index": idx,
                    "name": f"Monitor {idx} ({m['width']}x{m['height']})",
                    "width": m["width"],
                    "height": m["height"],
                })
            return monitors
    except Exception:
        return [{"index": 1, "name": "Monitor 1", "width": 1920, "height": 1080}]


class ScreenShareTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, fps: int = DEFAULT_FPS, max_width: int = DEFAULT_MAX_WIDTH, monitor_index: int = 1):
        super().__init__()
        self.fps = fps
        self.max_width = max_width
        self.monitor_index = monitor_index
        self._frame_interval = 1 / fps
        self._start_time = None
        self._frame_count = 0
        self._sct = None  # created lazily inside the dedicated capture thread
        # mss (and the underlying GDI handles on Windows) is not thread-safe —
        # a single-worker executor guarantees every grab() runs on the same
        # OS thread for this track's whole lifetime.
        self._executor = ThreadPoolExecutor(max_workers=1)

    def set_monitor(self, monitor_index: int) -> None:
        self.monitor_index = monitor_index

    async def recv(self):
        if self._start_time is None:
            self._start_time = time.time()
        else:
            target_time = self._start_time + self._frame_count * self._frame_interval
            wait = target_time - time.time()
            if wait > 0:
                await asyncio.sleep(wait)

        loop = asyncio.get_event_loop()
        img = await loop.run_in_executor(self._executor, self._grab_frame)

        frame = VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = int(self._frame_count * VIDEO_CLOCK_RATE * self._frame_interval)
        frame.time_base = Fraction(1, VIDEO_CLOCK_RATE)
        self._frame_count += 1
        return frame

    def _grab_frame(self):
        if self._sct is None:
            factory = getattr(mss, "MSS", mss.mss)
            self._sct = factory()

        monitors = self._sct.monitors
        idx = self.monitor_index
        if idx >= len(monitors) or idx < 0:
            idx = 1 if len(monitors) > 1 else 0

        shot = self._sct.grab(monitors[idx])
        img = np.array(shot)[:, :, :3]  # BGRA -> BGR

        height, width = img.shape[:2]
        if width > self.max_width:
            scale = self.max_width / width
            target_w = self.max_width
            target_h = int(height * scale)
            # Ensure dimensions are even for video codecs (libx264 / VP8)
            target_w -= target_w % 2
            target_h -= target_h % 2
            pil_img = Image.fromarray(img[:, :, ::-1])  # BGR -> RGB for PIL
            resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
            pil_img = pil_img.resize((target_w, target_h), resample_filter)
            img = np.array(pil_img)[:, :, ::-1].copy()  # RGB -> BGR back
        else:
            # Ensure width and height are even numbers
            h_even = height - (height % 2)
            w_even = width - (width % 2)
            if h_even != height or w_even != width:
                img = img[:h_even, :w_even]

        return img

    def stop(self):
        super().stop()
        self._executor.shutdown(wait=False)
