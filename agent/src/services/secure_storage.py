"""Encrypts the device credential at rest using Windows DPAPI (per-machine key,
managed by Windows itself) instead of writing the device token as plaintext —
required by the project's "no plaintext secrets when Windows has a secure
storage mechanism" rule."""

import json
from pathlib import Path

import win32crypt

from config.settings import CREDENTIALS_PATH


def save_credentials(device_id: str, device_token: str, path: Path = CREDENTIALS_PATH) -> None:
    payload = json.dumps({"device_id": device_id, "device_token": device_token}).encode("utf-8")
    encrypted = win32crypt.CryptProtectData(payload, "SentinelDesk Agent credentials", None, None, None, 0)
    path.write_bytes(encrypted)


def load_credentials(path: Path = CREDENTIALS_PATH) -> dict | None:
    if not path.exists():
        return None
    encrypted = path.read_bytes()
    _, decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
    return json.loads(decrypted.decode("utf-8"))
