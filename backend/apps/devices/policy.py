from django.utils import timezone

from apps.system_settings.models import SystemSettings


def get_ice_servers(settings_obj=None):
    """Returns WebRTC STUN and (if enabled) TURN ICE server configurations."""
    if settings_obj is None:
        settings_obj = SystemSettings.get_solo()
    servers = [{"urls": [settings_obj.stun_server_url or "stun:stun.l.google.com:19302"]}]
    if settings_obj.turn_server_enabled and settings_obj.turn_server_url:
        turn_entry = {"urls": [settings_obj.turn_server_url]}
        if settings_obj.turn_username:
            turn_entry["username"] = settings_obj.turn_username
        if settings_obj.turn_credential:
            turn_entry["credential"] = settings_obj.turn_credential
        servers.append(turn_entry)
    return servers


def get_agent_remote_payload(device_status=None, extra=None):
    """Builds standard policy and auto-update configuration returned to
    the agent during periodic heartbeat or metrics reporting."""
    settings_obj = SystemSettings.get_solo()
    payload = {
        "server_time": timezone.now(),
        "policy": {
            "metrics_interval_seconds": settings_obj.agent_metrics_interval_seconds,
            "screen_monitor_enabled": settings_obj.agent_screen_monitor_enabled,
            "usb_monitor_enabled": settings_obj.agent_usb_monitor_enabled,
            "app_usage_monitor_enabled": settings_obj.agent_app_usage_monitor_enabled,
            "browser_history_monitor_enabled": settings_obj.agent_browser_history_monitor_enabled,
            "file_activity_monitor_enabled": settings_obj.agent_file_activity_monitor_enabled,
            "idle_activity_monitor_enabled": settings_obj.agent_idle_activity_monitor_enabled,
            "system_error_monitor_enabled": settings_obj.agent_system_error_monitor_enabled,
        },
        "ice_servers": get_ice_servers(settings_obj),
    }
    if device_status:
        payload["status"] = device_status
    if settings_obj.agent_auto_update_enabled and settings_obj.agent_latest_version:
        payload["update"] = {
            "latest_version": settings_obj.agent_latest_version,
            "download_url": settings_obj.agent_download_url,
            "sha256": settings_obj.agent_sha256,
        }
    else:
        payload["update"] = None

    if extra:
        payload.update(extra)
    return payload

