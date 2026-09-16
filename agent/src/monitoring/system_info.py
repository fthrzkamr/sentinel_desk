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


def _hardware_identity() -> dict:
    """Manufacturer/model/serial number via WMI — not exposed by psutil/
    platform, but pywin32 (already a dependency) can query it directly, no
    extra package needed. Best-effort: some VMs/edge cases don't populate
    these, so any failure just leaves the fields blank rather than crashing
    enrollment over cosmetic data."""
    if platform.system() != "Windows":
        return {"manufacturer": "", "model": "", "serial_number": ""}

    try:
        import win32com.client

        wmi = win32com.client.GetObject("winmgmts:")
        manufacturer = ""
        model = ""
        for system in wmi.InstancesOf("Win32_ComputerSystem"):
            manufacturer = (system.Manufacturer or "").strip()
            model = (system.Model or "").strip()
            break
        serial_number = ""
        for bios in wmi.InstancesOf("Win32_BIOS"):
            serial_number = (bios.SerialNumber or "").strip()
            break
        return {"manufacturer": manufacturer, "model": model, "serial_number": serial_number}
    except Exception:  # noqa: BLE001 - hardware identity is optional metadata
        return {"manufacturer": "", "model": "", "serial_number": ""}


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
        **_hardware_identity(),
    }
