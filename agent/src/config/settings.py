import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _get_agent_dir() -> Path:
    """Directory the agent's own files (.env, credentials.dat, logs/) live
    next to. Once PyInstaller freezes this into a onefile .exe, `__file__`
    resolves inside the temporary per-run extraction folder (sys._MEIPASS)
    instead of anywhere stable — credentials saved there would vanish the
    moment the process exits. `sys.executable` is the actual .exe path in
    that case, so persistent state has to be anchored there instead."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


# Every monitor flag the agent currently knows about — used only by
# _ensure_msi_defaults() below to detect flags missing from an
# already-installed MSI device's .env (e.g. a feature added after that
# device was installed). Keep this in sync with AgentConfig's own fields.
_KNOWN_MONITOR_FLAGS = (
    "SCREEN_MONITOR_ENABLED",
    "USB_MONITOR_ENABLED",
    "APP_USAGE_MONITOR_ENABLED",
    "BROWSER_HISTORY_MONITOR_ENABLED",
    "FILE_ACTIVITY_MONITOR_ENABLED",
    "IDLE_ACTIVITY_MONITOR_ENABLED",
    "SYSTEM_ERROR_MONITOR_ENABLED",
)


def _ensure_msi_defaults(env_path: Path) -> None:
    """MSI-installed devices (see agent/installer/build.ps1) ship with
    every monitor flag explicitly true and an INSTALLED_VIA_MSI=true
    marker. Self-update only ever replaces the .exe, never .env — so a
    monitor flag added in a *later* agent version would otherwise silently
    default to disabled (AgentConfig.load()'s own safe fallback, meant for
    manually-configured devices) on a device installed before that flag
    existed. For a marked MSI install, append any flag missing from the
    file so it matches the "everything on" policy that install chose,
    instead of quietly falling back to opt-in-false."""
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    if not any(line.strip() == "INSTALLED_VIA_MSI=true" for line in lines):
        return

    existing_keys = {line.split("=", 1)[0].strip() for line in lines if "=" in line and not line.strip().startswith("#")}
    missing = [flag for flag in _KNOWN_MONITOR_FLAGS if flag not in existing_keys]
    if not missing:
        return

    with open(env_path, "a", encoding="utf-8") as f:
        f.write("\n")
        for flag in missing:
            f.write(f"{flag}=true\n")


AGENT_DIR = _get_agent_dir()
_ensure_msi_defaults(AGENT_DIR / ".env")
load_dotenv(AGENT_DIR / ".env")

CREDENTIALS_PATH = AGENT_DIR / "credentials.dat"


@dataclass
class AgentConfig:
    server_url: str
    enrollment_token: str | None
    monitor_interval: int
    screen_monitor_enabled: bool
    usb_monitor_enabled: bool
    app_usage_monitor_enabled: bool
    browser_history_monitor_enabled: bool
    file_activity_monitor_enabled: bool
    idle_activity_monitor_enabled: bool
    system_error_monitor_enabled: bool

    @classmethod
    def load(cls) -> "AgentConfig":
        server_url = os.environ.get("SERVER_URL", "http://localhost:8000")

        def _flag(name: str) -> bool:
            return os.environ.get(name, "false").lower() == "true"

        return cls(
            server_url=server_url.rstrip("/"),
            enrollment_token=os.environ.get("ENROLLMENT_TOKEN") or None,
            monitor_interval=int(os.environ.get("MONITOR_INTERVAL", "15")),
            screen_monitor_enabled=_flag("SCREEN_MONITOR_ENABLED"),
            usb_monitor_enabled=_flag("USB_MONITOR_ENABLED"),
            app_usage_monitor_enabled=_flag("APP_USAGE_MONITOR_ENABLED"),
            browser_history_monitor_enabled=_flag("BROWSER_HISTORY_MONITOR_ENABLED"),
            file_activity_monitor_enabled=_flag("FILE_ACTIVITY_MONITOR_ENABLED"),
            idle_activity_monitor_enabled=_flag("IDLE_ACTIVITY_MONITOR_ENABLED"),
            system_error_monitor_enabled=_flag("SYSTEM_ERROR_MONITOR_ENABLED"),
        )
