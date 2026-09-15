"""One-time system snapshot collected at enrollment time. Continuous realtime
metrics (CPU/RAM/disk usage over time) are added in Phase 3 — this module only
answers "what is this machine", not "how busy is it right now"."""

import getpass
import platform
import socket
import uuid

import psutil


def _mac_address() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> ele) & 0xFF:02X}" for ele in range(40, -8, -8))


def gather_system_info() -> dict:
    virtual_memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")

    return {
        "hostname": socket.gethostname(),
        "computer_name": socket.gethostname(),
        "username": getpass.getuser(),
        "os_name": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "cpu": platform.processor() or "Unknown",
        "ram": f"{virtual_memory.total // (1024 ** 3)} GB",
        "disk": f"{disk.total // (1024 ** 3)} GB",
        "mac_address": _mac_address(),
    }
