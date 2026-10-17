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
DEFAULT_FPS = 12
DEFAULT_MAX_WIDTH = 1280


class ScreenShareTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, fps: int = DEFAULT_FPS, max_width: int = DEFAULT_MAX_WIDTH):
        super().__init__()
        self.fps = fps
        self.max_width = max_width
        self._frame_interval = 1 / fps
        self._start_time = None
        self._frame_count = 0
        self._sct = None  # created lazily inside the dedicated capture thread
        # mss (and the underlying GDI handles on Windows) is not thread-safe —
        # a single-worker executor guarantees every grab() runs on the same
        # OS thread for this track's whole lifetime.
        self._executor = ThreadPoolExecutor(max_workers=1)

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
            self._sct = mss.mss()

        shot = self._sct.grab(self._sct.monitors[1])
        img = np.array(shot)[:, :, :3]  # BGRA -> BGR

        height, width = img.shape[:2]
        if width > self.max_width:
            scale = self.max_width / width
            new_size = (self.max_width, int(height * scale))
            pil_img = Image.fromarray(img[:, :, ::-1])  # BGR -> RGB for PIL
            pil_img = pil_img.resize(new_size, Image.BILINEAR)
            img = np.array(pil_img)[:, :, ::-1].copy()  # RGB -> BGR back

        return img

    def stop(self):
        super().stop()
        self._executor.shutdown(wait=False)
