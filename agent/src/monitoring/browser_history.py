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

BROWSER_USER_DATA_DIRS = {
    "Chrome": os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
    "Edge": os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
}

MAX_ENTRIES_PER_SYNC = 500


def _profile_history_paths(user_data_dir: str) -> list[str]:
    """"Default" is only the first profile ever created on a machine — most
    corporate laptops end up on "Profile 1", "Profile 2", etc. once someone
    signs in with a work account (or just adds a second profile), and each
    profile has its own separate History file. Checking only "Default" silently
    missed every one of those, with no error to point at why."""
    if not os.path.isdir(user_data_dir):
        return []
    paths = []
    for entry in os.scandir(user_data_dir):
        if not entry.is_dir():
            continue
        if entry.name == "Default" or entry.name.startswith("Profile "):
            history_path = os.path.join(entry.path, "History")
            if os.path.exists(history_path):
                paths.append(history_path)
    return paths


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
            # Chrome Sync merges browsing history from every device signed
            # into the same Google account into this SAME local History
            # file - a site opened on the user's phone shows up in
            # `urls`/`visits` here too, with no visible difference unless
            # you check `visit_source`. Chrome only writes a visit_source
            # row for non-local origins (SOURCE_BROWSED, the common case,
            # is deliberately never stored - see Chromium's
            # visit_source.cc) - source=0 is SOURCE_SYNCED, so a LEFT JOIN
            # that excludes it is what keeps this to "actually browsed on
            # this laptop", which is the whole point of this monitor.
            # Querying `visits` (one row per visit event) instead of
            # `urls` (one row per URL, latest visit time only) is what
            # makes that per-visit check possible in the first place.
            cursor = conn.execute(
                "SELECT u.url, u.title, v.visit_time FROM visits v "
                "JOIN urls u ON v.url = u.id "
                "LEFT JOIN visit_source vs ON vs.id = v.id "
                "WHERE v.visit_time > ? AND (vs.source IS NULL OR vs.source != 0) "
                "ORDER BY v.visit_time ASC LIMIT ?",
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
        self._pending_synced_at: datetime.datetime | None = None

    def collect_new_entries(self) -> list[dict]:
        now = datetime.datetime.utcnow()
        entries: list[dict] = []
        for browser, user_data_dir in BROWSER_USER_DATA_DIRS.items():
            for history_path in _profile_history_paths(user_data_dir):
                entries.extend(_read_new_entries(browser, history_path, self._last_synced_at))
        if entries:
            self._pending_synced_at = now
        else:
            self._last_synced_at = now
            self._pending_synced_at = None
        return entries

    def mark_synced(self) -> None:
        if self._pending_synced_at is not None:
            self._last_synced_at = self._pending_synced_at
            self._pending_synced_at = None
