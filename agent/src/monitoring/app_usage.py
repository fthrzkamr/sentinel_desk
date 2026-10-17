"""Attributes elapsed wall-clock time to whichever application window is in
the foreground. `sample()` is called every metrics cycle (cheap — just two
Win32 calls); `flush()` returns the accumulated per-app-per-day seconds as
a list ready to send, then resets so the next sync only reports the delta."""

import datetime
import logging

logger = logging.getLogger("sentineldesk.agent")

# A gap this long between samples means the machine was asleep/locked for a
# while — attributing it entirely to whatever app happened to be focused
# right before sleeping would wildly overstate that app's usage.
MAX_ATTRIBUTABLE_GAP_SECONDS = 300


def _foreground_app() -> tuple[str | None, str]:
    import psutil
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None, ""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        app_name = psutil.Process(pid).name()
    except Exception:  # noqa: BLE001 - process may have exited between the two calls
        return None, ""
    title = win32gui.GetWindowText(hwnd) or ""
    return app_name, title


class AppUsageTracker:
    def __init__(self):
        self._last_sample_at: datetime.datetime | None = None
        self._durations: dict[tuple[str, datetime.date], int] = {}
        self._titles: dict[tuple[str, datetime.date], str] = {}

    def sample(self) -> None:
        now = datetime.datetime.now()
        app_name, title = _foreground_app()

        if self._last_sample_at is not None and app_name:
            elapsed = (now - self._last_sample_at).total_seconds()
            if 0 < elapsed < MAX_ATTRIBUTABLE_GAP_SECONDS:
                key = (app_name, now.date())
                self._durations[key] = self._durations.get(key, 0) + int(elapsed)
                if title:
                    self._titles[key] = title

        self._last_sample_at = now

    def flush(self) -> list[dict]:
        items = [
            {
                "app_name": app_name,
                "window_title": self._titles.get((app_name, date), ""),
                "date": date.isoformat(),
                "duration_seconds": seconds,
            }
            for (app_name, date), seconds in self._durations.items()
            if seconds > 0
        ]
        self._durations.clear()
        self._titles.clear()
        return items
