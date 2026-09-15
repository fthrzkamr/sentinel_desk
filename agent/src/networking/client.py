import logging

import requests

from config.settings import AgentConfig

logger = logging.getLogger("sentineldesk.agent")


class EnrollmentError(Exception):
    pass


def enroll(config: AgentConfig, system_info: dict) -> dict:
    if not config.enrollment_token:
        raise EnrollmentError("ENROLLMENT_TOKEN is not set in agent .env")

    response = requests.post(
        f"{config.server_url}/api/agent/enroll/",
        json={"token": config.enrollment_token, **system_info},
        timeout=15,
    )
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
