"""Reads Error/Critical-level entries from the device's own local Windows
Event Log — System and Application channels only (not Security, which is a
different kind of data entirely and out of scope). Read-only: nothing is
ever written to the event log, and no input is ever injected — this is
purely for IT to see driver crashes, hardware failures, and unexpected
shutdowns without needing physical/RDP access to open Event Viewer."""

import datetime
import logging

import win32evtlog
import win32evtlogutil
import winerror

logger = logging.getLogger("sentineldesk.agent")

LOG_NAMES = ("System", "Application")
MAX_ENTRIES_PER_SYNC = 200

# The classic Win32 event log API (used below) only exposes one severity —
# EVENTLOG_ERROR_TYPE — for both "Error" and "Critical" entries; the
# Critical/Warning/Verbose distinction only exists in the newer XML-based
# Windows Event Log schema, which needs a heavier EvtQuery-based read this
# module doesn't do. Verified directly on this machine: every entry here
# comes back as EVENTLOG_ERROR_TYPE regardless of its real severity. So
# instead of trusting the OS's own (unavailable) severity, CRITICAL is
# decided by a curated list of providers known to indicate hardware
# failure or an unexpected shutdown — everything else is ERROR.
_CRITICAL_PROVIDERS = {
    "disk",  # physical disk I/O failures
    "Ntfs",  # filesystem corruption
    "volsnap",  # volume/shadow-copy failures, often disk-related
    "Microsoft-Windows-Kernel-Power",  # unexpected shutdown/reboot (e.g. event 41, the classic "dirty shutdown")
    "Microsoft-Windows-WHEA-Logger",  # Windows Hardware Error Architecture — CPU/memory hardware faults
}


def _level_name(event_type: int, provider: str) -> str | None:
    if event_type != win32evtlog.EVENTLOG_ERROR_TYPE:
        return None
    return "CRITICAL" if provider in _CRITICAL_PROVIDERS else "ERROR"


def _read_new_entries(log_name: str, since: datetime.datetime) -> list[dict]:
    handle = None
    try:
        handle = win32evtlog.OpenEventLog(None, log_name)
    except Exception as exc:  # noqa: BLE001 - a missing/inaccessible log shouldn't break the sync loop
        logger.info("Could not open %s event log (%s)", log_name, exc)
        return []

    entries = []
    try:
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        while len(entries) < MAX_ENTRIES_PER_SYNC:
            try:
                records = win32evtlog.ReadEventLog(handle, flags, 0)
            except Exception as exc:  # noqa: BLE001
                if getattr(exc, "winerror", None) == winerror.ERROR_HANDLE_EOF:
                    break
                logger.info("Error reading %s event log (%s)", log_name, exc)
                break
            if not records:
                break

            stop = False
            for record in records:
                occurred_at = record.TimeGenerated
                if occurred_at <= since:
                    stop = True
                    break

                level = _level_name(record.EventType, record.SourceName)
                if level is None:
                    continue

                try:
                    message = win32evtlogutil.SafeFormatMessage(record, log_name)
                except Exception:  # noqa: BLE001 - message-DLL resolution can fail per-provider, message is optional
                    message = ""

                # TimeGenerated comes back as a naive pywintypes.datetime that
                # is actually local time (verified directly against
                # datetime.now() on this machine — NOT UTC despite having no
                # tzinfo attached). astimezone() with no args interprets a
                # naive datetime as system-local and attaches the correct
                # UTC offset, rather than mislabeling it as UTC outright.
                aware_occurred_at = datetime.datetime(
                    occurred_at.year,
                    occurred_at.month,
                    occurred_at.day,
                    occurred_at.hour,
                    occurred_at.minute,
                    occurred_at.second,
                ).astimezone()
                entries.append(
                    {
                        "log_name": log_name,
                        "provider": record.SourceName,
                        "event_id": record.EventID & 0xFFFF,
                        "level": level,
                        "message": (message or "").strip(),
                        "occurred_at": aware_occurred_at.isoformat(),
                    }
                )
                if len(entries) >= MAX_ENTRIES_PER_SYNC:
                    break

            if stop:
                break
    finally:
        win32evtlog.CloseEventLog(handle)

    return entries


class SystemErrorTracker:
    def __init__(self):
        # First sync only looks back an hour, same rationale as
        # BrowserHistoryTracker — report ongoing activity, not a dump of
        # this machine's entire error history the moment monitoring turns on.
        self._last_synced_at = datetime.datetime.now() - datetime.timedelta(hours=1)
        self._pending_synced_at: datetime.datetime | None = None

    def collect_new_entries(self) -> list[dict]:
        now = datetime.datetime.now()
        entries: list[dict] = []
        for log_name in LOG_NAMES:
            entries.extend(_read_new_entries(log_name, self._last_synced_at))
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
