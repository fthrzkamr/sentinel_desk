import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent.parent.parent
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
