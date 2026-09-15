"""Registers the packaged agent .exe to launch automatically at Windows
login, via the per-user Registry Run key — no admin rights needed, and it
only ever affects the current Windows user (never system-wide), matching
this being a per-user endpoint agent rather than a system service."""

import logging
import sys

logger = logging.getLogger("sentineldesk.agent")

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "SentinelDeskAgent"


def install() -> None:
    if not getattr(sys, "frozen", False):
        logger.info("Running from source, not a packaged .exe — skipping auto-start registration.")
        return

    import winreg

    exe_path = sys.executable
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        logger.info("Registered to auto-start at login (%s)", exe_path)
    except OSError as exc:
        logger.warning("Could not register auto-start (%s) — agent will still work, just not launch automatically", exc)


def uninstall() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
        logger.info("Removed auto-start registration.")
    except FileNotFoundError:
        logger.info("Auto-start was not registered — nothing to remove.")
    except OSError as exc:
        logger.warning("Could not remove auto-start registration (%s)", exc)


def is_installed() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, RUN_VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
