import logging
import os
import shutil
import signal
import sys
import time

from config.settings import AGENT_DIR, AgentConfig
from monitoring.app_usage import AppUsageTracker
from monitoring.browser_history import BrowserHistoryTracker
from monitoring.compliance import gather_compliance_status
from monitoring.file_watcher import FileActivityWatcher
from monitoring.hardware_details import gather_hardware_details
from monitoring.idle_tracker import IdleActivityTracker
from monitoring.location import get_os_location
from monitoring.metrics import MetricsCollector
from monitoring.software_inventory import gather_installed_software
from monitoring.system_errors import SystemErrorTracker
from monitoring.system_info import gather_system_info
from monitoring.usb_watcher import UsbWatcher
from networking.client import (
    EnrollmentError,
    enroll,
    send_app_usage,
    send_browsing_history,
    send_file_activity,
    send_idle_activity,
    send_location,
    send_metrics,
    send_software_sync,
    send_system_errors,
    send_usb_event,
)
from screen.signaling_client import LiveScreenAgent
from services import autostart, hardening
from services.secure_storage import load_credentials, save_credentials
from services.updater import (
    apply_update,
    cleanup_old_update_file,
    download_and_verify_binary,
    is_newer_version,
)

AGENT_VERSION = "0.8.17"
MAX_BACKOFF_SECONDS = 300
SOFTWARE_SYNC_INTERVAL_SECONDS = 3600  # software list changes rarely — no need to resend every cycle
LOCATION_SYNC_INTERVAL_SECONDS = 900  # 15 min — frequent enough to track a moving laptop, not spammy
APP_USAGE_SYNC_INTERVAL_SECONDS = 300
IDLE_ACTIVITY_SYNC_INTERVAL_SECONDS = 300
BROWSER_HISTORY_SYNC_INTERVAL_SECONDS = 60
FILE_ACTIVITY_SYNC_INTERVAL_SECONDS = 120
SYSTEM_ERROR_SYNC_INTERVAL_SECONDS = 300
COMPLIANCE_CHECK_INTERVAL_SECONDS = 3600  # BitLocker/firewall/AV can flip mid-session, unlike hardware specs

LOG_DIR = AGENT_DIR / "logs"


def _configure_file_logging() -> None:
    """Deferred rather than run unconditionally at import time. The
    --install-hardening/--uninstall-hardening CLI paths (see __main__ below)
    run this exact exe as SYSTEM (Product.wxs's InstallHardening custom
    action, Impersonate="no") - if this ran at import time like it used to,
    SYSTEM would be the one creating logs/agent.log for the very first time.
    A file's creator gets an automatic CREATOR OWNER grant on it; everyone
    else only gets whatever the folder's own ACL happens to hand out, which
    on a fresh ProgramData folder is Read+Execute for standard users - not
    enough to append to it. That produced a PermissionError on every
    subsequent launch by the real Scheduled-Task-launched standard-user
    process, no matter what ACL was granted on the *folder* (icacls on the
    parent folder proved unreliable to apply here across several attempts,
    and is unnecessary once this is fixed at the source instead). Calling
    this only from run() - the one path that's always launched as the
    standard user, never as SYSTEM - guarantees that user is always the
    file's first creator and therefore always has full rights to it
    afterward. The --install-hardening/--uninstall-hardening/
    --uninstall-autostart CLI paths never call this and don't need to -
    they already print straight to the console (AttachConsole below)."""
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


def poll_usb(
    config: AgentConfig,
    device_id: str,
    device_token: str,
    watcher: UsbWatcher,
    file_activity_watcher: FileActivityWatcher | None,
):
    connected, disconnected = watcher.poll()
    for event in connected:
        if file_activity_watcher:
            file_activity_watcher.track_removable(event["drive_letter"])
        send_usb_event(config, device_id, device_token, {"event": "connected", **event})
        watcher.acknowledge_connected(event["drive_letter"], event["label"], event["serial"])
        logger.info("USB connected - %s (%s)", event["label"] or event["drive_letter"], event["drive_letter"])
    for drive_letter in disconnected:
        if file_activity_watcher:
            file_activity_watcher.untrack_removable(drive_letter)
        send_usb_event(config, device_id, device_token, {"event": "disconnected", "drive_letter": drive_letter})
        watcher.acknowledge_disconnected(drive_letter)
        logger.info("USB disconnected - %s", drive_letter)


def sync_app_usage(config: AgentConfig, device_id: str, device_token: str, tracker: AppUsageTracker):
    items = tracker.pending()
    if items:
        send_app_usage(config, device_id, device_token, items)
        tracker.clear()
        logger.info("App usage synced - %s app(s)", len(items))


def sync_idle_activity(config: AgentConfig, device_id: str, device_token: str, tracker: IdleActivityTracker):
    items = tracker.pending()
    if items:
        send_idle_activity(config, device_id, device_token, items)
        tracker.clear()
        logger.info("Idle activity synced - %s day(s)", len(items))


def sync_browsing_history(config: AgentConfig, device_id: str, device_token: str, tracker: BrowserHistoryTracker):
    items = tracker.collect_new_entries()
    if items:
        send_browsing_history(config, device_id, device_token, items)
        tracker.mark_synced()
        logger.info("Browsing history synced - %s entr(ies)", len(items))


def sync_file_activity(config: AgentConfig, device_id: str, device_token: str, watcher: FileActivityWatcher):
    items = watcher.poll()
    if items:
        send_file_activity(config, device_id, device_token, items)
        watcher.clear_pending()
        logger.info("File activity synced - %s event(s)", len(items))


def sync_system_errors(config: AgentConfig, device_id: str, device_token: str, tracker: SystemErrorTracker):
    items = tracker.collect_new_entries()
    if items:
        send_system_errors(config, device_id, device_token, items)
        tracker.mark_synced()
        logger.info("System errors synced - %s entr(ies)", len(items))


def _cleanup_stale_runtime_extractions() -> None:
    """The onefile bootloader (see SentinelDeskAgent.spec's runtime_tmpdir)
    extracts a fresh ~70-100MB copy of itself into _runtime\\_MEI<id> on
    EVERY launch - confirmed live, there's no actual content-hash reuse
    despite the fixed path. It only cleans that folder up on its own on a
    graceful exit; a force-killed process (Watchdog's own stuck-dialog
    recovery does exactly this, see watchdog_service.py's
    _agent_stuck_on_dialog) leaves it behind. Left unchecked these pile up
    forever - confirmed live, one laptop's ProgramData\\SentinelDesk folder
    had grown to ~500MB of orphaned extractions after a day of repeated
    kill/relaunch cycles. Safe to delete any _MEI* folder other than this
    process's own (sys._MEIPASS) - anything else under _runtime is, by
    definition, left over from a process that already exited one way or
    another."""
    if not getattr(sys, "frozen", False):
        return
    runtime_dir = AGENT_DIR / "_runtime"
    own_extraction = os.path.basename(getattr(sys, "_MEIPASS", ""))
    try:
        entries = list(runtime_dir.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name == own_extraction:
            continue
        try:
            shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            pass


def _apply_remote_policy(
    policy: dict,
    config: AgentConfig,
    trackers: dict,
    device_id: str,
    device_token: str,
) -> None:
    interval = policy.get("metrics_interval_seconds")
    if interval and isinstance(interval, int) and 5 <= interval <= 300:
        if interval != config.monitor_interval:
            logger.info("Remote policy updated monitor interval: %ss -> %ss", config.monitor_interval, interval)
            config.monitor_interval = interval

    screen_enabled = policy.get("screen_monitor_enabled")
    if screen_enabled is not None and screen_enabled != config.screen_monitor_enabled:
        config.screen_monitor_enabled = screen_enabled
        logger.info("Remote policy changed screen monitoring to %s", screen_enabled)
        if screen_enabled:
            if not trackers["live_screen"]:
                agent = LiveScreenAgent(config.server_url, device_id, device_token)
                agent.start_in_background()
                trackers["live_screen"] = agent
        else:
            if trackers["live_screen"]:
                trackers["live_screen"].stop()
                trackers["live_screen"] = None

    flag_map = [
        ("usb_monitor_enabled", "usb", UsbWatcher),
        ("app_usage_monitor_enabled", "app_usage", AppUsageTracker),
        ("browser_history_monitor_enabled", "browser_history", BrowserHistoryTracker),
        ("file_activity_monitor_enabled", "file_activity", FileActivityWatcher),
        ("idle_activity_monitor_enabled", "idle_activity", IdleActivityTracker),
        ("system_error_monitor_enabled", "system_error", SystemErrorTracker),
    ]
    for key, tracker_key, cls in flag_map:
        val = policy.get(key)
        if val is not None and val != getattr(config, key, None):
            setattr(config, key, val)
            logger.info("Remote policy changed %s to %s", key, val)
            if val and not trackers[tracker_key]:
                try:
                    trackers[tracker_key] = cls()
                except Exception as exc:
                    logger.warning("Could not initialize %s tracker (%s)", tracker_key, exc)
            elif not val and trackers[tracker_key]:
                trackers[tracker_key] = None


def run():
    _configure_file_logging()
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    _cleanup_stale_runtime_extractions()
    cleanup_old_update_file()

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

    trackers = {
        "usb": UsbWatcher() if config.usb_monitor_enabled else None,
        "app_usage": AppUsageTracker() if config.app_usage_monitor_enabled else None,
        "browser_history": BrowserHistoryTracker() if config.browser_history_monitor_enabled else None,
        "file_activity": FileActivityWatcher() if config.file_activity_monitor_enabled else None,
        "idle_activity": IdleActivityTracker() if config.idle_activity_monitor_enabled else None,
        "system_error": SystemErrorTracker() if config.system_error_monitor_enabled else None,
        "live_screen": live_screen_agent,
    }
    for enabled, name in [
        (config.usb_monitor_enabled, "USB"),
        (config.app_usage_monitor_enabled, "App usage"),
        (config.browser_history_monitor_enabled, "Browser history"),
        (config.file_activity_monitor_enabled, "File activity"),
        (config.idle_activity_monitor_enabled, "Idle activity"),
        (config.system_error_monitor_enabled, "System error"),
    ]:
        logger.info("%s monitoring %s", name, "enabled" if enabled else "disabled")
    last_app_usage_sync = time.monotonic()
    last_browser_history_sync = time.monotonic()
    last_file_activity_sync = time.monotonic()
    last_idle_activity_sync = time.monotonic()
    last_system_error_sync = time.monotonic()
    hardware_details_sent = False
    last_compliance_check = 0.0  # 0 forces a check on the very first loop iteration

    backoff = 1
    while not _shutdown_requested:
        try:
            system_info = gather_system_info()
            metrics = collector.collect()
            payload = {**metrics, "username": system_info["username"], "agent_version": AGENT_VERSION}

            if not hardware_details_sent:
                # WMI queries for these (GPU/RAM sticks/disks/battery/BIOS)
                # have real overhead — worth it once at startup so an
                # already-enrolled device fills in the fuller spec sheet
                # too, but not worth repeating every 15s like the rest of
                # this payload. Only flips True after this call actually
                # succeeds, so a failed first attempt just retries next cycle.
                try:
                    payload.update(gather_hardware_details())
                except Exception as exc:  # noqa: BLE001 - spec data is optional, never block metrics over it
                    logger.warning("Could not gather hardware details (%s)", exc)
                # manufacturer/model/system_family/serial_number were only
                # ever sent at enroll time - a device enrolled before a
                # fix to this data (or before the field existed at all)
                # stayed stuck showing "Not Available" forever after,
                # since nothing ever re-sent it short of a full re-enroll.
                # system_info already has these (gather_system_info() just
                # ran above, this reuses that result instead of querying
                # WMI again) - piggybacking on this same once-per-startup
                # block backfills it for every already-enrolled device too.
                for field in ("manufacturer", "model", "system_family", "serial_number"):
                    if system_info.get(field):
                        payload[field] = system_info[field]

            if time.monotonic() - last_compliance_check >= COMPLIANCE_CHECK_INTERVAL_SECONDS:
                try:
                    payload.update(gather_compliance_status())
                    last_compliance_check = time.monotonic()
                except Exception as exc:  # noqa: BLE001 - optional, never block metrics over it
                    logger.warning("Could not gather compliance status (%s)", exc)

            result = send_metrics(config, device_id, device_token, payload)
            hardware_details_sent = True
            logger.info(
                "Metrics OK - status=%s cpu=%s%% ram=%s%% disk=%s%%",
                result.get("status"),
                metrics["cpu_percent"],
                metrics["ram_percent"],
                metrics["disk_percent"],
            )

            if isinstance(result, dict):
                if "policy" in result and isinstance(result["policy"], dict):
                    _apply_remote_policy(result["policy"], config, trackers, device_id, device_token)

                update_info = result.get("update")
                if update_info and isinstance(update_info, dict):
                    latest_ver = update_info.get("latest_version", "")
                    download_url = update_info.get("download_url", "")
                    sha256_hash = update_info.get("sha256", "")
                    if latest_ver and download_url and sha256_hash and is_newer_version(latest_ver, AGENT_VERSION):
                        logger.info("New agent update available: %s (current: %s)", latest_ver, AGENT_VERSION)
                        update_dest = AGENT_DIR / "updates" / f"SentinelDeskAgent-{latest_ver}.exe"
                        if download_and_verify_binary(
                            download_url,
                            sha256_hash,
                            config.server_url,
                            device_id,
                            device_token,
                            update_dest,
                        ):
                            apply_update(update_dest)

            backoff = 1
        except Exception as exc:  # noqa: BLE001 - any network/HTTP failure should trigger reconnect+backoff
            err_msg = str(exc)
            if "pending admin approval" in err_msg.lower():
                logger.info("Perangkat menunggu persetujuan (Pending Approval) oleh Admin di dashboard. Menunggu...")
                time.sleep(10)
                continue
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

        if trackers["usb"]:
            try:
                poll_usb(config, device_id, device_token, trackers["usb"], trackers["file_activity"])
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("USB polling failed (%s)", exc)

        if trackers["app_usage"]:
            trackers["app_usage"].sample()
            if time.monotonic() - last_app_usage_sync >= APP_USAGE_SYNC_INTERVAL_SECONDS:
                try:
                    sync_app_usage(config, device_id, device_token, trackers["app_usage"])
                except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                    logger.warning("App usage sync failed (%s), will retry next interval", exc)
                last_app_usage_sync = time.monotonic()

        if trackers["idle_activity"]:
            trackers["idle_activity"].sample()
            if time.monotonic() - last_idle_activity_sync >= IDLE_ACTIVITY_SYNC_INTERVAL_SECONDS:
                try:
                    sync_idle_activity(config, device_id, device_token, trackers["idle_activity"])
                except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                    logger.warning("Idle activity sync failed (%s), will retry next interval", exc)
                last_idle_activity_sync = time.monotonic()

        if trackers["browser_history"] and time.monotonic() - last_browser_history_sync >= BROWSER_HISTORY_SYNC_INTERVAL_SECONDS:
            try:
                sync_browsing_history(config, device_id, device_token, trackers["browser_history"])
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("Browsing history sync failed (%s), will retry next interval", exc)
            last_browser_history_sync = time.monotonic()

        if trackers["file_activity"] and time.monotonic() - last_file_activity_sync >= FILE_ACTIVITY_SYNC_INTERVAL_SECONDS:
            try:
                sync_file_activity(config, device_id, device_token, trackers["file_activity"])
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("File activity sync failed (%s), will retry next interval", exc)
            last_file_activity_sync = time.monotonic()

        if trackers["system_error"] and time.monotonic() - last_system_error_sync >= SYSTEM_ERROR_SYNC_INTERVAL_SECONDS:
            try:
                sync_system_errors(config, device_id, device_token, trackers["system_error"])
            except Exception as exc:  # noqa: BLE001 - don't let this break the metrics loop
                logger.warning("System error sync failed (%s), will retry next interval", exc)
            last_system_error_sync = time.monotonic()

        time.sleep(config.monitor_interval)

    if trackers["live_screen"]:
        trackers["live_screen"].stop()
    logger.info("SentinelDesk Agent stopped gracefully.")
    # The live-screen signaling/WebRTC background threads can block a clean
    # interpreter exit on Windows even after every other thread is done.
    os._exit(0)


if __name__ == "__main__":
    if "--uninstall-autostart" in sys.argv:
        autostart.uninstall()
        sys.exit(0)
    if "--install-hardening" in sys.argv or "--uninstall-hardening" in sys.argv:
        # One-time, admin-run step — not something the zero-admin enrollment
        # flow or the auto-update channel can trigger on its own. See
        # services/hardening.py for exactly what this does and does not do.
        #
        # This exe is built windowed (no console of its own — see the .spec),
        # so plain print() here would go nowhere when run from PowerShell.
        # Attach to whatever console launched us so the admin actually sees
        # the result instead of a silent no-op. Best-effort, wrapped: this
        # runs from Product.wxs's InstallHardening custom action as a
        # deferred, SYSTEM-context (Impersonate="no") process spawned by
        # msiexec, which doesn't reliably have an attachable parent console
        # the way an interactive admin's own elevated prompt does -
        # AttachConsole(-1) succeeding there is not guaranteed, and
        # open("CONOUT$", ...) can still fail even when it does. Letting
        # either raise uncaught here would surface as the generic
        # "Traceback is disabled via bootloader option" dialog (from this
        # exe's own disable_windowed_traceback=True) - a bad admin-feedback
        # message is still far better than that showing up in the middle of
        # an otherwise-working install.
        import ctypes

        try:
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w")
                sys.stderr = open("CONOUT$", "w")
        except OSError:
            pass

        # Built onedir (a folder), not onefile — see SentinelDeskWatchdog.spec
        # for why — so the exe sits one level deeper than the agent's own.
        watchdog_exe = str(AGENT_DIR / "SentinelDeskWatchdog" / "SentinelDeskWatchdog.exe")
        try:
            if "--install-hardening" in sys.argv:
                hardening.install(sys.executable, watchdog_exe)
                logger.info("Hardening installed (via --install-hardening CLI).")
                print("Hardening installed.")
            else:
                hardening.uninstall(watchdog_exe)
                logger.info("Hardening removed (via --uninstall-hardening CLI).")
                print("Hardening removed.")
        except Exception as exc:  # noqa: BLE001 - any failure here must degrade to a message, never a crash dialog
            # This path deliberately never calls _configure_file_logging()
            # (see its docstring), so logger.error here has no file handler
            # to write to - it still reaches the console via Python's
            # last-resort stderr fallback, same destination AttachConsole
            # already redirected above (when that succeeded), so the
            # print() right after is what actually guarantees this is seen.
            logger.error("Hardening command failed: %s", exc)
            print(f"Failed: {exc}")
            sys.exit(1)
        sys.exit(0)

    try:
        run()
    except SystemExit:
        raise  # a plain sys.exit() (e.g. EnrollmentError above) is an intentional, already-logged exit
    except Exception:
        # Deployed to employee laptops - this process must never surface a
        # crash dialog to whoever is using the machine, no matter what goes
        # wrong (server unreachable, a bug we didn't foresee, anything).
        # logger.exception needs _configure_file_logging() to have already
        # run for this to land in agent.log - that's the very first thing
        # run() does, so this only loses its record in the rare case that
        # setup itself is what failed; either way, exiting quietly here is
        # strictly better than a popup, and the Watchdog Service relaunches
        # within ~30s regardless (see watchdog_service.py).
        logger.exception("Unhandled error in agent - exiting quietly for Watchdog to relaunch.")
        sys.exit(1)
