import logging
import os
import signal
import sys
import time
from pathlib import Path

from config.settings import AgentConfig
from monitoring.location import get_os_location
from monitoring.metrics import MetricsCollector
from monitoring.software_inventory import gather_installed_software
from monitoring.system_info import gather_system_info
from networking.client import EnrollmentError, enroll, send_location, send_metrics, send_software_sync
from screen.signaling_client import LiveScreenAgent
from services.secure_storage import load_credentials, save_credentials

AGENT_VERSION = "0.1.0-dev"
MAX_BACKOFF_SECONDS = 300
SOFTWARE_SYNC_INTERVAL_SECONDS = 3600  # software list changes rarely — no need to resend every cycle
LOCATION_SYNC_INTERVAL_SECONDS = 900  # 15 min — frequent enough to track a moving laptop, not spammy

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("sentineldesk.agent")

_shutdown_requested = False


def _handle_shutdown_signal(signum, frame):
    global _shutdown_requested
    logger.info("Shutdown signal received, stopping after current cycle...")
    _shutdown_requested = True


def get_or_create_credentials(config: AgentConfig) -> dict:
    credentials = load_credentials()
    if credentials:
        logger.info("Loaded existing credentials for device %s", credentials["device_id"])
        return credentials

    logger.info("No stored credentials found, starting enrollment...")
    system_info = gather_system_info()
    result = enroll(config, {**system_info, "agent_version": AGENT_VERSION})
    save_credentials(result["device_id"], result["device_token"])
    logger.info("Enrollment successful, device_id=%s", result["device_id"])
    return result


def sync_software(config: AgentConfig, device_id: str, device_token: str):
    items = gather_installed_software()
    result = send_software_sync(config, device_id, device_token, items)
    logger.info("Software inventory synced - %s item(s)", result.get("synced", len(items)))


def sync_location(config: AgentConfig, device_id: str, device_token: str):
    location = get_os_location()
    result = send_location(config, device_id, device_token, location)
    if location:
        logger.info("Location synced - source=OS lat=%.4f lng=%.4f", location["latitude"], location["longitude"])
    else:
        logger.info("Location synced - source=%s (OS location unavailable)", result.get("source", "IP"))


def run():
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)

    config = AgentConfig.load()
    logger.info("SentinelDesk Agent starting (server=%s)", config.server_url)

    try:
        credentials = get_or_create_credentials(config)
    except EnrollmentError as exc:
        logger.error("Could not enroll this device: %s", exc)
        sys.exit(1)

    device_id = credentials["device_id"]
    device_token = credentials["device_token"]
    collector = MetricsCollector()

    live_screen_agent = None
    if config.screen_monitor_enabled:
        live_screen_agent = LiveScreenAgent(config.server_url, device_id, device_token)
        live_screen_agent.start_in_background()
        logger.info("Live-screen signaling started")
    else:
        logger.info("Live-screen monitoring disabled on this device (SCREEN_MONITOR_ENABLED=false)")

    try:
        sync_software(config, device_id, device_token)
    except Exception as exc:  # noqa: BLE001 - inventory sync failure shouldn't block metrics/heartbeat
        logger.warning("Initial software sync failed (%s), will retry later", exc)
    last_software_sync = time.monotonic()

    try:
        sync_location(config, device_id, device_token)
    except Exception as exc:  # noqa: BLE001 - location sync failure shouldn't block metrics/heartbeat
        logger.warning("Initial location sync failed (%s), will retry later", exc)
    last_location_sync = time.monotonic()

    backoff = 1
    while not _shutdown_requested:
        try:
            system_info = gather_system_info()
            metrics = collector.collect()
            payload = {**metrics, "username": system_info["username"], "agent_version": AGENT_VERSION}
            result = send_metrics(config, device_id, device_token, payload)
            logger.info(
                "Metrics OK - status=%s cpu=%s%% ram=%s%% disk=%s%%",
                result["status"],
                metrics["cpu_percent"],
                metrics["ram_percent"],
                metrics["disk_percent"],
            )
            backoff = 1
        except Exception as exc:  # noqa: BLE001 - any network/HTTP failure should trigger reconnect+backoff
            logger.warning("Sending metrics failed (%s), retrying in %ss", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            continue

        if time.monotonic() - last_software_sync >= SOFTWARE_SYNC_INTERVAL_SECONDS:
            try:
                sync_software(config, device_id, device_token)
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("Software sync failed (%s), will retry next interval", exc)
            last_software_sync = time.monotonic()

        if time.monotonic() - last_location_sync >= LOCATION_SYNC_INTERVAL_SECONDS:
            try:
                sync_location(config, device_id, device_token)
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("Location sync failed (%s), will retry next interval", exc)
            last_location_sync = time.monotonic()

        time.sleep(config.monitor_interval)

    if live_screen_agent:
        live_screen_agent.stop()
    logger.info("SentinelDesk Agent stopped gracefully.")
    # The overlay's Tkinter mainloop runs on a daemon thread that can block a
    # clean interpreter exit on Windows even after every other thread is done.
    os._exit(0)


if __name__ == "__main__":
    run()
