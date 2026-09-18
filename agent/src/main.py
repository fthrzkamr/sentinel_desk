import logging
import os
import signal
import sys
import time

from config.settings import AGENT_DIR, AgentConfig
from monitoring.app_usage import AppUsageTracker
from monitoring.browser_history import BrowserHistoryTracker
from monitoring.file_watcher import FileActivityWatcher
from monitoring.location import get_os_location
from monitoring.metrics import MetricsCollector
from monitoring.software_inventory import gather_installed_software
from monitoring.system_info import gather_system_info
from monitoring.usb_watcher import UsbWatcher
from networking.client import (
    EnrollmentError,
    enroll,
    send_app_usage,
    send_browsing_history,
    send_file_activity,
    send_location,
    send_metrics,
    send_software_sync,
    send_usb_event,
)
from screen.signaling_client import LiveScreenAgent
from services import autostart
from services.secure_storage import load_credentials, save_credentials

AGENT_VERSION = "0.1.0-dev"
MAX_BACKOFF_SECONDS = 300
SOFTWARE_SYNC_INTERVAL_SECONDS = 3600  # software list changes rarely — no need to resend every cycle
LOCATION_SYNC_INTERVAL_SECONDS = 900  # 15 min — frequent enough to track a moving laptop, not spammy
APP_USAGE_SYNC_INTERVAL_SECONDS = 300
BROWSER_HISTORY_SYNC_INTERVAL_SECONDS = 60
FILE_ACTIVITY_SYNC_INTERVAL_SECONDS = 120

LOG_DIR = AGENT_DIR / "logs"
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


def poll_usb(config: AgentConfig, device_id: str, device_token: str, watcher: UsbWatcher):
    connected, disconnected = watcher.poll()
    for event in connected:
        send_usb_event(config, device_id, device_token, {"event": "connected", **event})
        logger.info("USB connected - %s (%s)", event["label"] or event["drive_letter"], event["drive_letter"])
    for drive_letter in disconnected:
        send_usb_event(config, device_id, device_token, {"event": "disconnected", "drive_letter": drive_letter})
        logger.info("USB disconnected - %s", drive_letter)


def sync_app_usage(config: AgentConfig, device_id: str, device_token: str, tracker: AppUsageTracker):
    items = tracker.flush()
    if items:
        send_app_usage(config, device_id, device_token, items)
        logger.info("App usage synced - %s app(s)", len(items))


def sync_browsing_history(config: AgentConfig, device_id: str, device_token: str, tracker: BrowserHistoryTracker):
    items = tracker.collect_new_entries()
    if items:
        send_browsing_history(config, device_id, device_token, items)
        logger.info("Browsing history synced - %s entr(ies)", len(items))


def sync_file_activity(config: AgentConfig, device_id: str, device_token: str, watcher: FileActivityWatcher):
    items = watcher.poll()
    if items:
        send_file_activity(config, device_id, device_token, items)
        logger.info("File activity synced - %s event(s)", len(items))


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

    autostart.install()

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

    usb_watcher = UsbWatcher() if config.usb_monitor_enabled else None
    app_usage_tracker = AppUsageTracker() if config.app_usage_monitor_enabled else None
    browser_history_tracker = BrowserHistoryTracker() if config.browser_history_monitor_enabled else None
    file_activity_watcher = FileActivityWatcher() if config.file_activity_monitor_enabled else None
    for enabled, name in [
        (config.usb_monitor_enabled, "USB"),
        (config.app_usage_monitor_enabled, "App usage"),
        (config.browser_history_monitor_enabled, "Browser history"),
        (config.file_activity_monitor_enabled, "File activity"),
    ]:
        logger.info("%s monitoring %s", name, "enabled" if enabled else "disabled")
    last_app_usage_sync = time.monotonic()
    last_browser_history_sync = time.monotonic()
    last_file_activity_sync = time.monotonic()

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

        if usb_watcher:
            try:
                poll_usb(config, device_id, device_token, usb_watcher)
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("USB polling failed (%s)", exc)

        if app_usage_tracker:
            app_usage_tracker.sample()
            if time.monotonic() - last_app_usage_sync >= APP_USAGE_SYNC_INTERVAL_SECONDS:
                try:
                    sync_app_usage(config, device_id, device_token, app_usage_tracker)
                except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                    logger.warning("App usage sync failed (%s), will retry next interval", exc)
                last_app_usage_sync = time.monotonic()

        if browser_history_tracker and time.monotonic() - last_browser_history_sync >= BROWSER_HISTORY_SYNC_INTERVAL_SECONDS:
            try:
                sync_browsing_history(config, device_id, device_token, browser_history_tracker)
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("Browsing history sync failed (%s), will retry next interval", exc)
            last_browser_history_sync = time.monotonic()

        if file_activity_watcher and time.monotonic() - last_file_activity_sync >= FILE_ACTIVITY_SYNC_INTERVAL_SECONDS:
            try:
                sync_file_activity(config, device_id, device_token, file_activity_watcher)
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("File activity sync failed (%s), will retry next interval", exc)
            last_file_activity_sync = time.monotonic()

        time.sleep(config.monitor_interval)

    if live_screen_agent:
        live_screen_agent.stop()
    logger.info("SentinelDesk Agent stopped gracefully.")
    # The live-screen signaling/WebRTC background threads can block a clean
    # interpreter exit on Windows even after every other thread is done.
    os._exit(0)


if __name__ == "__main__":
    if "--uninstall-autostart" in sys.argv:
        autostart.uninstall()
        sys.exit(0)
    run()
