import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import AgentConfig

logger = logging.getLogger("sentineldesk.agent")

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Reuses an underlying HTTP connection pool with Keep-Alive to avoid
    costly repeated TCP/TLS handshakes across frequent agent telemetry posts."""
    global _session
    if _session is None:
        _session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retries)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    return _session


class EnrollmentError(Exception):
    pass


def enroll(config: AgentConfig, system_info: dict) -> dict:
    try:
        token = config.enrollment_token or ""
        response = get_session().post(
            f"{config.server_url}/api/agent/enroll/",
            json={"token": token, **system_info},
            timeout=15,
        )
    except requests.exceptions.RequestException as exc:
        raise EnrollmentError(f"Could not reach server at {config.server_url} ({exc})") from exc

    if response.status_code != 201:
        raise EnrollmentError(f"Enrollment failed ({response.status_code}): {response.text}")

    return response.json()


def send_heartbeat(config: AgentConfig, device_id: str, device_token: str, payload: dict) -> dict:
    response = get_session().post(
        f"{config.server_url}/api/agent/heartbeat/",
        json=payload,
        headers={
            "X-Device-ID": device_id,
            "Authorization": f"DeviceToken {device_token}",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def send_metrics(config: AgentConfig, device_id: str, device_token: str, payload: dict) -> dict:
    response = get_session().post(
        f"{config.server_url}/api/agent/metrics/",
        json=payload,
        headers={
            "X-Device-ID": device_id,
            "Authorization": f"DeviceToken {device_token}",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def send_software_sync(config: AgentConfig, device_id: str, device_token: str, items: list) -> dict:
    response = get_session().post(
        f"{config.server_url}/api/agent/software/",
        json={"items": items},
        headers={
            "X-Device-ID": device_id,
            "Authorization": f"DeviceToken {device_token}",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_location(config: AgentConfig, device_id: str, device_token: str, location: dict | None) -> dict:
    response = get_session().post(
        f"{config.server_url}/api/agent/location/",
        json=location or {},
        headers={
            "X-Device-ID": device_id,
            "Authorization": f"DeviceToken {device_token}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def send_app_usage(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = get_session().post(
        f"{config.server_url}/api/agent/app-usage/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_browsing_history(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = get_session().post(
        f"{config.server_url}/api/agent/browsing-history/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=20,
    )
    response.raise_for_status()


def send_file_activity(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = get_session().post(
        f"{config.server_url}/api/agent/file-activity/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_idle_activity(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = get_session().post(
        f"{config.server_url}/api/agent/idle-activity/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_system_errors(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = get_session().post(
        f"{config.server_url}/api/agent/system-errors/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_usb_event(config: AgentConfig, device_id: str, device_token: str, payload: dict) -> None:
    response = get_session().post(
        f"{config.server_url}/api/agent/usb-event/",
        json=payload,
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=10,
    )
    response.raise_for_status()


def rotate_device_token(config: AgentConfig, device_id: str, device_token: str) -> str:
    """Rotates the device token with the server and returns the new raw token."""
    response = get_session().post(
        f"{config.server_url}/api/agent/rotate-token/",
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("device_token")
