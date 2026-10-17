"""Polls a set of folders and diffs file mtimes against the previous
snapshot. Not a real filesystem event hook (that would need the `watchdog`
package and a background OS-level watch thread) — a plain poll matches this
agent's existing polling design and needs no extra dependency, at the cost
of only catching activity between polls rather than every single event as
it happens.

Two kinds of folders are tracked, distinguished by `source` on each event:
- LOCAL: Desktop/Documents/Downloads, watched for the device's whole
  lifetime.
- USB: a removable drive's root, added the moment UsbWatcher reports it
  connected and removed the moment it disconnects — this is what lets a
  "file copied onto external media" alert be raised with real evidence
  instead of just inferring it from the USB connect event alone."""

import datetime
import logging
import os

from .file_activity_types import Source

logger = logging.getLogger("sentineldesk.agent")

WATCHED_FOLDER_NAMES = ["Desktop", "Documents", "Downloads"]


def _local_folders() -> list[str]:
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
        self._snapshots: dict[str, dict[str, float]] = {}
        self._sources: dict[str, str] = {}
        for folder in _local_folders():
            self._snapshots[folder] = _snapshot(folder)
            self._sources[folder] = Source.LOCAL

    def track_removable(self, drive_letter: str) -> None:
        """Starts watching a just-connected removable drive's root folder.
        Baseline snapshot is taken immediately so only files that appear
        *after* this point count as activity — files already on the drive
        before it was plugged into this machine aren't this device's doing."""
        folder = f"{drive_letter}\\"
        if folder in self._snapshots:
            return
        self._snapshots[folder] = _snapshot(folder)
        self._sources[folder] = Source.USB
        logger.info("Now watching removable drive %s for file activity", drive_letter)

    def untrack_removable(self, drive_letter: str) -> None:
        folder = f"{drive_letter}\\"
        self._snapshots.pop(folder, None)
        self._sources.pop(folder, None)

    def poll(self) -> list[dict]:
        events: list[dict] = []
        now = datetime.datetime.utcnow().isoformat() + "Z"

        for folder in list(self._sources):
            # Skip fixed local folders that always exist — only removable
            # drives can vanish out from under us mid-poll (unplugged
            # between the USB "disconnected" event and this cycle).
            source = self._sources[folder]
            previous = self._snapshots.get(folder, {})
            current = _snapshot(folder) if source == Source.LOCAL or os.path.isdir(folder) else {}

            for path, mtime in current.items():
                if path not in previous:
                    events.append({"event_type": "CREATED", "path": path, "occurred_at": now, "source": source})
                elif mtime > previous[path]:
                    events.append({"event_type": "MODIFIED", "path": path, "occurred_at": now, "source": source})

            for path in previous:
                if path not in current:
                    events.append({"event_type": "DELETED", "path": path, "occurred_at": now, "source": source})

            self._snapshots[folder] = current

        return events
