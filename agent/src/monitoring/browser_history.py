"""Reads new entries out of Chrome/Edge's own local History SQLite database.
Both browsers keep that file open while running, so we copy it to a temp
file first (a plain file copy, unlike sqlite3.connect, isn't blocked by the
browser's lock) and query the copy instead of the live file."""

import datetime
import logging
import os
import shutil
import sqlite3
import tempfile

logger = logging.getLogger("sentineldesk.agent")

CHROME_EPOCH = datetime.datetime(1601, 1, 1)

BROWSER_HISTORY_PATHS = {
    "Chrome": os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History"),
    "Edge": os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History"),
}

MAX_ENTRIES_PER_SYNC = 500


def _webkit_to_iso(webkit_timestamp: int) -> str:
    return (CHROME_EPOCH + datetime.timedelta(microseconds=webkit_timestamp)).isoformat() + "Z"


def _read_new_entries(browser: str, path: str, since: datetime.datetime) -> list[dict]:
    if not os.path.exists(path):
        return []

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        shutil.copy2(path, tmp_path)

        since_webkit = int((since - CHROME_EPOCH).total_seconds() * 1_000_000)
        conn = sqlite3.connect(tmp_path)
        try:
            cursor = conn.execute(
                "SELECT url, title, last_visit_time FROM urls WHERE last_visit_time > ? "
                "ORDER BY last_visit_time ASC LIMIT ?",
                (since_webkit, MAX_ENTRIES_PER_SYNC),
            )
            return [
                {"browser": browser, "url": url, "title": title or "", "visited_at": _webkit_to_iso(visited)}
                for url, title, visited in cursor.fetchall()
                if url
            ]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - locked/missing/corrupt history shouldn't break the main loop
        logger.info("Could not read %s history (%s)", browser, exc)
        return []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


class BrowserHistoryTracker:
    def __init__(self):
        # First sync only looks back an hour — this agent reports ongoing
        # activity, not a one-time dump of someone's entire browsing history.
        self._last_synced_at = datetime.datetime.utcnow() - datetime.timedelta(hours=1)

    def collect_new_entries(self) -> list[dict]:
        entries: list[dict] = []
        for browser, path in BROWSER_HISTORY_PATHS.items():
            entries.extend(_read_new_entries(browser, path, self._last_synced_at))
        self._last_synced_at = datetime.datetime.utcnow()
        return entries
