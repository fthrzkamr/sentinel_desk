"""Polling-based USB/removable-drive detector. Windows has no simple
cross-process "USB inserted" signal without a native window message pump
(WM_DEVICECHANGE), which this headless agent doesn't have — so instead we
just re-enumerate removable drive letters every metrics cycle and diff
against what we saw last time. Cheap enough to run every cycle."""

import logging
import string

logger = logging.getLogger("sentineldesk.agent")


def _removable_drives() -> dict[str, tuple[str, str]]:
    import win32api
    import win32file

    drives: dict[str, tuple[str, str]] = {}
    try:
        bitmask = win32api.GetLogicalDrives()
    except Exception as exc:  # noqa: BLE001 - never let USB polling break the main loop
        logger.warning("Could not enumerate drives (%s)", exc)
        return drives

    for i, letter in enumerate(string.ascii_uppercase):
        if not (bitmask >> i) & 1:
            continue
        root = f"{letter}:\\"
        try:
            if win32file.GetDriveType(root) != win32file.DRIVE_REMOVABLE:
                continue
            label, serial, *_ = win32api.GetVolumeInformation(root)
            drives[f"{letter}:"] = (label or "", str(serial))
        except Exception:  # noqa: BLE001 - drive not ready / no media in it yet
            continue
    return drives


class UsbWatcher:
    def __init__(self):
        self._known: dict[str, tuple[str, str]] = {}

    def poll(self) -> tuple[list[dict], list[str]]:
        """Returns (connected_events, disconnected_drive_letters)."""
        current = _removable_drives()
        connected = [
            {"drive_letter": letter, "label": label, "serial": serial}
            for letter, (label, serial) in current.items()
            if letter not in self._known
        ]
        disconnected = [letter for letter in self._known if letter not in current]

        self._known = current
        return connected, disconnected
