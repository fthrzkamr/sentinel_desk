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


AGENT_DIR = _get_agent_dir()
load_dotenv(AGENT_DIR / ".env")

CREDENTIALS_PATH = AGENT_DIR / "credentials.dat"


@dataclass
class AgentConfig:
    server_url: str
    enrollment_token: str | None
    monitor_interval: int
    screen_monitor_enabled: bool

    @classmethod
    def load(cls) -> "AgentConfig":
        server_url = os.environ.get("SERVER_URL", "http://localhost:8000")
        return cls(
            server_url=server_url.rstrip("/"),
            enrollment_token=os.environ.get("ENROLLMENT_TOKEN") or None,
            monitor_interval=int(os.environ.get("MONITOR_INTERVAL", "15")),
            screen_monitor_enabled=os.environ.get("SCREEN_MONITOR_ENABLED", "false").lower() == "true",
        )
