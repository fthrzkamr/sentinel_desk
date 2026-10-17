"""One-time system snapshot collected at enrollment time. Continuous realtime
metrics (CPU/RAM/disk usage over time) are added in Phase 3 — this module only
answers "what is this machine", not "how busy is it right now"."""

import getpass
import platform
import socket
import uuid

import psutil

from .hardware_details import gather_hardware_details


def _mac_address() -> str:
    """The MAC of whichever adapter actually carries this machine's
    outbound traffic - not uuid.getnode(), which Python's own docs admit
    "the MAC address of any one of [the machine's interfaces] may be
    returned" on a multi-NIC machine, with no guarantee it's the same one
    on every call. Confirmed live: this is exactly what caused a real
    duplicate Device record for the same physical laptop - a re-enroll
    picked a different virtual adapter's MAC (Wi-Fi Direct, Bluetooth
    Network Connection) than the original enrollment had, so the backend's
    MAC-match lookup found nothing and created a second device instead of
    reusing the first.

    Connecting a UDP socket doesn't send any packets (UDP is connectionless
    - this only asks the OS to resolve which local interface it WOULD use
    for that destination) but it does make the OS populate getsockname()
    with the real outbound-facing local IP, which can then be matched back
    to that interface's MAC in psutil.net_if_addrs(). This is the same
    adapter the agent's own HTTP requests to server_url actually go out
    on, so it's the most meaningful "this machine's identity" signal
    available - and, unlike uuid.getnode(), it stays consistent across
    enrollments as long as the primary network path doesn't change."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
        for addrs in psutil.net_if_addrs().values():
            if not any(a.family == socket.AF_INET and a.address == local_ip for a in addrs):
                continue
            for addr in addrs:
                if addr.family == psutil.AF_LINK and addr.address:
                    return addr.address.upper().replace("-", ":")
    except OSError:
        pass
    # Fallback for the rare case the routing lookup above fails outright
    # (e.g. no network route at all yet) - not reliably stable on a
    # multi-NIC machine, but better than crashing enrollment over this.
    node = uuid.getnode()
    return ":".join(f"{(node >> ele) & 0xFF:02X}" for ele in range(40, -8, -8))


def _hardware_identity() -> dict:
    """Manufacturer/model/serial number via WMI — not exposed by psutil/
    platform, but pywin32 (already a dependency) can query it directly, no
    extra package needed. Best-effort: some VMs/edge cases don't populate
    these, so any failure just leaves the fields blank rather than crashing
    enrollment over cosmetic data."""
    if platform.system() != "Windows":
        return {"manufacturer": "", "model": "", "system_family": "", "serial_number": ""}

    try:
        import win32com.client

        wmi = win32com.client.GetObject("winmgmts:")
        manufacturer = ""
        model = ""
        system_family = ""
        for system in wmi.InstancesOf("Win32_ComputerSystem"):
            manufacturer = (system.Manufacturer or "").strip()
            model = (system.Model or "").strip()
            # Win32_ComputerSystem.Model is a manufacturer MTM/part code
            # ("20T3S2WY00" on Lenovo) - meaningless to anyone who isn't
            # that manufacturer's own support database. SystemFamily is
            # the actual marketing name ("ThinkPad X13 Gen 1") printed on
            # the laptop itself, which is what lets this be compared
            # against a human-entered asset description at all. Not every
            # OEM populates it, so it's kept separate rather than replacing
            # Model - better to have both than silently lose the MTM code.
            system_family = (getattr(system, "SystemFamily", "") or "").strip()
            break
        serial_number = ""
        for bios in wmi.InstancesOf("Win32_BIOS"):
            serial_number = (bios.SerialNumber or "").strip()
            break
        return {
            "manufacturer": manufacturer,
            "model": model,
            "system_family": system_family,
            "serial_number": serial_number,
        }
    except Exception:  # noqa: BLE001 - hardware identity is optional metadata
        return {"manufacturer": "", "model": "", "system_family": "", "serial_number": ""}


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
