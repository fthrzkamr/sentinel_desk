"""Buckets active-vs-idle wall-clock time per day, based on Windows'
GetLastInputInfo — the exact same system-wide "when did a mouse/keyboard
event last happen" API Windows itself uses for screensaver/away detection.
This only ever answers *when* input last happened, never *what* it was —
nothing resembling a keylogger. Mirrors app_usage.py's sample()-then-
flush()-the-delta pattern so an agent restart only loses the seconds it
never got to report, never double-counts."""

import ctypes
import datetime
import logging

logger = logging.getLogger("sentineldesk.agent")

# A gap this long between samples means the machine was asleep/locked —
# that whole gap shouldn't count as either "idle" or "active" time worked.
MAX_ATTRIBUTABLE_GAP_SECONDS = 300


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _idle_seconds() -> float:
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(_LastInputInfo)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    millis_idle = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis_idle / 1000.0


class IdleActivityTracker:
    def __init__(self):
        self._last_sample_at: datetime.datetime | None = None
        self._active_seconds: dict[datetime.date, int] = {}
        self._idle_seconds: dict[datetime.date, int] = {}

    def sample(self) -> None:
        now = datetime.datetime.now()

        if self._last_sample_at is not None:
            elapsed = (now - self._last_sample_at).total_seconds()
            if 0 < elapsed < MAX_ATTRIBUTABLE_GAP_SECONDS:
                try:
                    idle_for = _idle_seconds()
                except Exception as exc:  # noqa: BLE001 - best-effort, never block the metrics loop
                    logger.info("Could not read idle time (%s)", exc)
                    idle_for = 0.0

                date = now.date()
                # Idle time shorter than this sample's own gap means input
                # happened at some point during the gap — count the whole
                # gap as active rather than trying to split it precisely.
                if idle_for < elapsed:
                    self._active_seconds[date] = self._active_seconds.get(date, 0) + int(elapsed)
                else:
                    self._idle_seconds[date] = self._idle_seconds.get(date, 0) + int(elapsed)

        self._last_sample_at = now

    def pending(self) -> list[dict]:
        dates = set(self._active_seconds) | set(self._idle_seconds)
        return [
            {
                "date": date.isoformat(),
                "active_seconds": self._active_seconds.get(date, 0),
                "idle_seconds": self._idle_seconds.get(date, 0),
            }
            for date in dates
        ]

    def clear(self) -> None:
        self._active_seconds.clear()
        self._idle_seconds.clear()

    def flush(self) -> list[dict]:
        items = self.pending()
        self.clear()
        return items
