"""Polls the top level of Desktop/Documents/Downloads and diffs file mtimes
against the previous snapshot. Not a real filesystem event hook (that would
need the `watchdog` package and a background OS-level watch thread) — a
plain poll matches this agent's existing polling design and needs no extra
dependency, at the cost of only catching activity between polls rather than
every single event as it happens."""

import datetime
import logging
import os

logger = logging.getLogger("sentineldesk.agent")

WATCHED_FOLDER_NAMES = ["Desktop", "Documents", "Downloads"]


def _watched_folders() -> list[str]:
    home = os.path.expanduser("~")
    return [
        os.path.join(home, name) for name in WATCHED_FOLDER_NAMES if os.path.isdir(os.path.join(home, name))
    ]


def _snapshot(folder: str) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    try:
        for entry in os.scandir(folder):
            if entry.is_file(follow_symlinks=False):
                try:
                    snapshot[entry.path] = entry.stat().st_mtime
                except OSError:
                    continue
    except OSError as exc:
        logger.info("Could not scan %s (%s)", folder, exc)
    return snapshot


class FileActivityWatcher:
    def __init__(self):
        self._snapshots: dict[str, dict[str, float]] = {folder: _snapshot(folder) for folder in _watched_folders()}

    def poll(self) -> list[dict]:
        events: list[dict] = []
        now = datetime.datetime.utcnow().isoformat() + "Z"

        for folder in _watched_folders():
            previous = self._snapshots.get(folder, {})
            current = _snapshot(folder)

            for path, mtime in current.items():
                if path not in previous:
                    events.append({"event_type": "CREATED", "path": path, "occurred_at": now})
                elif mtime > previous[path]:
                    events.append({"event_type": "MODIFIED", "path": path, "occurred_at": now})

            for path in previous:
                if path not in current:
                    events.append({"event_type": "DELETED", "path": path, "occurred_at": now})

            self._snapshots[folder] = current

        return events
