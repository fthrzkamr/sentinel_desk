import hashlib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from networking.client import get_session

logger = logging.getLogger("sentineldesk.agent")


def parse_version(version_str: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", str(version_str))
    return tuple(int(x) for x in nums) if nums else (0,)


def is_newer_version(candidate: str, current: str) -> bool:
    try:
        return parse_version(candidate) > parse_version(current)
    except Exception:
        return False


def cleanup_old_update_file() -> None:
    """Removes any stale .exe.old left behind from a previous self-update."""
    if not getattr(sys, "frozen", False):
        return
    old_file = Path(sys.executable).with_suffix(".exe.old")
    if old_file.exists():
        try:
            old_file.unlink()
            logger.info("Cleaned up previous update file %s", old_file)
        except OSError:
            pass


def download_and_verify_binary(
    download_url: str,
    expected_sha256: str,
    server_url: str,
    device_id: str,
    device_token: str,
    target_path: Path,
) -> bool:
    full_url = download_url if download_url.startswith("http") else f"{server_url.rstrip('/')}{download_url}"
    logger.info("Downloading agent update from %s ...", full_url)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".tmp")

    hasher = hashlib.sha256()
    try:
        session = get_session()
        with session.get(
            full_url,
            stream=True,
            headers={"X-Device-ID": device_id, "Authorization": f"DeviceToken {device_token}"},
            timeout=60,
        ) as resp:
            resp.raise_for_status()
            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
    except Exception as exc:
        logger.warning("Failed to download agent update: %s", exc)
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        return False

    calculated_hash = hasher.hexdigest().lower()
    expected_hash = expected_sha256.lower().strip()
    if calculated_hash != expected_hash:
        logger.error(
            "Agent update SHA-256 mismatch! expected=%s calculated=%s. Discarding update.",
            expected_hash,
            calculated_hash,
        )
        temp_path.unlink(missing_ok=True)
        return False

    if target_path.exists():
        target_path.unlink(missing_ok=True)
    temp_path.rename(target_path)
    logger.info("Agent update verified successfully (sha256=%s)", calculated_hash)
    return True


def apply_update(new_binary_path: Path) -> None:
    if not getattr(sys, "frozen", False):
        logger.info(
            "Agent is running from source (dev mode). New binary verified at %s. Skipping process replacement.",
            new_binary_path,
        )
        return

    current_exe = Path(sys.executable)
    old_exe = current_exe.with_suffix(".exe.old")
    try:
        if old_exe.exists():
            old_exe.unlink()
        current_exe.rename(old_exe)
        new_binary_path.rename(current_exe)
        logger.info("Agent binary replaced. Relaunching %s ...", current_exe)
        subprocess.Popen([str(current_exe)])
        sys.exit(0)
    except Exception as exc:
        logger.error("Failed to apply binary update (%s)", exc)

