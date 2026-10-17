import logging

import requests

from config.settings import AgentConfig

logger = logging.getLogger("sentineldesk.agent")


class EnrollmentError(Exception):
    pass


def enroll(config: AgentConfig, system_info: dict) -> dict:
    if not config.enrollment_token:
        raise EnrollmentError("ENROLLMENT_TOKEN is not set in agent .env")

    # The server being unreachable (not yet started, network down, wrong
    # SERVER_URL) is routine, expected-to-happen-sometimes behavior, not a
    # bug - the Watchdog Service relaunches this process ~30s later either
    # way, so it should be handled exactly like a bad enrollment response
    # (log once, exit, let the next scheduled run retry), not crash. Only
    # this first network call needs this: everything in run()'s main loop
    # after a successful enrollment is already wrapped in broad
    # except-Exception handlers with their own retry/backoff.
    try:
        response = requests.post(
            f"{config.server_url}/api/agent/enroll/",
            json={"token": config.enrollment_token, **system_info},
            timeout=15,
        )
    except requests.exceptions.RequestException as exc:
        raise EnrollmentError(f"Could not reach server at {config.server_url} ({exc})") from exc

    if response.status_code != 201:
        raise EnrollmentError(f"Enrollment failed ({response.status_code}): {response.text}")

    return response.json()


def send_heartbeat(config: AgentConfig, device_id: str, device_token: str, payload: dict) -> dict:
    response = requests.post(
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
    response = requests.post(
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
    response = requests.post(
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
    response = requests.post(
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
    response = requests.post(
        f"{config.server_url}/api/agent/app-usage/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_browsing_history(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = requests.post(
        f"{config.server_url}/api/agent/browsing-history/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=20,
    )
    response.raise_for_status()


def send_file_activity(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = requests.post(
        f"{config.server_url}/api/agent/file-activity/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_idle_activity(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = requests.post(
        f"{config.server_url}/api/agent/idle-activity/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_system_errors(config: AgentConfig, device_id: str, device_token: str, items: list) -> None:
    response = requests.post(
        f"{config.server_url}/api/agent/system-errors/",
        json={"items": items},
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    response.raise_for_status()


def send_usb_event(config: AgentConfig, device_id: str, device_token: str, payload: dict) -> None:
    response = requests.post(
        f"{config.server_url}/api/agent/usb-event/",
        json=payload,
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=10,
    )
    response.raise_for_status()
