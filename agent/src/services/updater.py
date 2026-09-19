"""Self-update: periodically ask the server what version is current, and if
it's newer than this running build, download + verify + swap the .exe and
relaunch. No admin needs to touch each laptop again after the first
install to push out a new build."""

import hashlib
import logging
import os
import subprocess
import sys
import tempfile

import requests

from config.settings import AGENT_DIR, AgentConfig

logger = logging.getLogger("sentineldesk.agent")


class UpdateError(Exception):
    pass


def check_for_update(config: AgentConfig, device_id: str, device_token: str, current_version: str) -> dict | None:
    response = requests.get(
        f"{config.server_url}/api/agent/version/",
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        timeout=15,
    )
    if response.status_code == 404:
        return None  # no active release configured on the server
    response.raise_for_status()
    data = response.json()
    if data["version"] == current_version:
        return None
    return data


def download_and_verify(
    config: AgentConfig, device_id: str, device_token: str, expected_sha256: str, expected_size: int
) -> str:
    """Downloads the active release next to the current exe, verifying its
    sha256 + size before returning the path — raises instead of ever
    handing back a file that didn't check out byte-for-byte."""
    dest_path = AGENT_DIR / "SentinelDeskAgent_new.exe"
    hasher = hashlib.sha256()
    size = 0

    with requests.get(
        f"{config.server_url}/api/agent/download/",
        headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
        stream=True,
        timeout=180,
    ) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                hasher.update(chunk)
                size += len(chunk)

    if size != expected_size or hasher.hexdigest() != expected_sha256:
        dest_path.unlink(missing_ok=True)
        raise UpdateError(f"Downloaded build failed verification (size={size}, sha256={hasher.hexdigest()})")

    return str(dest_path)


def apply_update_and_restart(new_exe_path: str) -> None:
    """Windows won't let a running .exe overwrite itself, so the swap has to
    happen from a separate, short-lived helper process after this one has
    fully exited. Spawns a detached batch script that waits, kills any
    lingering copy of this exe (belt-and-suspenders — this process is about
    to exit on its own), replaces it with the new build, and relaunches."""
    if not getattr(sys, "frozen", False):
        logger.warning("Not running as a packaged .exe — skipping self-update swap (dev/source run).")
        return

    current_exe = sys.executable
    exe_name = os.path.basename(current_exe)
    script_path = os.path.join(tempfile.gettempdir(), "sentineldesk_update.bat")
    script = (
        "@echo off\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        f'taskkill /F /IM "{exe_name}" >nul 2>&1\r\n'
        "timeout /t 1 /nobreak >nul\r\n"
        f'move /Y "{new_exe_path}" "{current_exe}"\r\n'
        f'start "" "{current_exe}"\r\n'
        'del "%~f0"\r\n'
    )
    with open(script_path, "w") as f:
        f.write(script)

    logger.info("Update downloaded and verified — restarting to apply it.")
    subprocess.Popen(
        ["cmd", "/c", script_path],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    sys.exit(0)
