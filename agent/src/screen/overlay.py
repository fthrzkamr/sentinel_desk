"""Always-on-top banner shown on the device's own screen while it's being
live-viewed. Required by design — live screen must never be silent/hidden
from the person sitting at the machine. Runs its own Tkinter mainloop in a
dedicated thread so it doesn't interfere with the agent's asyncio loops."""

import logging
import queue
import threading
import tkinter as tk

logger = logging.getLogger("sentineldesk.agent")

BANNER_TEXT = "SentinelDesk: layar ini sedang dipantau oleh administrator"


class ScreenShareOverlay:
    def __init__(self):
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="livescreen-overlay")
        self._thread.start()

    def _run(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception as exc:  # noqa: BLE001 - no display/desktop session available
            logger.warning("Screen-share overlay unavailable (%s) — monitoring will still work, just without the on-screen banner", exc)
            return

        banner = {"window": None}

        def poll():
            try:
                while True:
                    action = self._queue.get_nowait()
                    if action == "show" and banner["window"] is None:
                        banner["window"] = self._create_banner(root)
                    elif action == "hide" and banner["window"] is not None:
                        banner["window"].destroy()
                        banner["window"] = None
            except queue.Empty:
                pass
            root.after(200, poll)

        root.after(200, poll)
        root.mainloop()

    @staticmethod
    def _create_banner(root):
        window = tk.Toplevel(root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="#dc2626")
        width = window.winfo_screenwidth()
        window.geometry(f"{width}x28+0+0")
        label = tk.Label(
            window,
            text=BANNER_TEXT,
            bg="#dc2626",
            fg="white",
            font=("Segoe UI", 10, "bold"),
        )
        label.pack(fill="both", expand=True)
        return window

    def show(self):
        self._queue.put("show")

    def hide(self):
        self._queue.put("hide")
