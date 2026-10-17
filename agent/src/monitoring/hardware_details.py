"""Detailed hardware spec collection via WMI, gathered once at enrollment
time. Every query is wrapped in its own try/except — a machine that doesn't
expose one WMI class (VMs, older BIOS, an unusual disk controller) should
still enroll successfully with whatever the others could find, rather than
losing the whole spec snapshot over one missing class."""

import logging

logger = logging.getLogger("sentineldesk.agent")


def _wmi():
    import win32com.client

    return win32com.client.GetObject("winmgmts:")


def _cpu_details() -> dict:
    try:
        wmi = _wmi()
        for cpu in wmi.InstancesOf("Win32_Processor"):
            return {
                "cpu_cores": int(cpu.NumberOfCores or 0) or None,
                "cpu_threads": int(cpu.NumberOfLogicalProcessors or 0) or None,
                "cpu_speed_mhz": int(cpu.MaxClockSpeed or 0) or None,
            }
    except Exception as exc:  # noqa: BLE001 - best-effort spec data
        logger.info("Could not read CPU details (%s)", exc)
    return {"cpu_cores": None, "cpu_threads": None, "cpu_speed_mhz": None}


def _motherboard_and_bios() -> dict:
    result = {"motherboard": "", "bios_version": ""}
    try:
        wmi = _wmi()
        for board in wmi.InstancesOf("Win32_BaseBoard"):
            manufacturer = (board.Manufacturer or "").strip()
            product = (board.Product or "").strip()
            result["motherboard"] = f"{manufacturer} {product}".strip()
            break
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read motherboard (%s)", exc)
    try:
        wmi = _wmi()
        for bios in wmi.InstancesOf("Win32_BIOS"):
            result["bios_version"] = (bios.SMBIOSBIOSVersion or "").strip()
            break
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read BIOS version (%s)", exc)
    return result


def _gpu_details() -> list[dict]:
    gpus = []
    try:
        wmi = _wmi()
        for gpu in wmi.InstancesOf("Win32_VideoController"):
            name = (gpu.Name or "").strip()
            if not name:
                continue
            adapter_ram = getattr(gpu, "AdapterRAM", None)
            # AdapterRAM is a 32-bit field in WMI — it wraps around to a
            # small/negative-looking number on cards with >4GB VRAM, so a
            # wrapped value is reported as unknown rather than a wrong one.
            vram_mb = None
            if adapter_ram and 0 < adapter_ram < 4 * 1024**3:
                vram_mb = int(adapter_ram / (1024**2))
            gpus.append(
                {
                    "name": name,
                    "driver_version": (getattr(gpu, "DriverVersion", "") or "").strip(),
                    "vram_mb": vram_mb,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read GPU details (%s)", exc)
    return gpus


def _ram_details() -> list[dict]:
    sticks = []
    try:
        wmi = _wmi()
        for stick in wmi.InstancesOf("Win32_PhysicalMemory"):
            capacity = getattr(stick, "Capacity", None)
            sticks.append(
                {
                    "capacity_gb": round(int(capacity) / (1024**3), 1) if capacity else None,
                    "speed_mhz": int(stick.Speed) if getattr(stick, "Speed", None) else None,
                    "manufacturer": (getattr(stick, "Manufacturer", "") or "").strip(),
                    "slot": (getattr(stick, "DeviceLocator", "") or "").strip(),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read RAM stick details (%s)", exc)
    return sticks


_MEDIA_TYPE_NAMES = {3: "HDD", 4: "SSD", 5: "SCM"}


def _disk_media_types() -> dict[str, str]:
    """MSFT_PhysicalDisk (root\\Microsoft\\Windows\\Storage) is the only WMI
    class that actually distinguishes SSD from HDD — Win32_DiskDrive's own
    MediaType field is almost always just the unhelpful "Fixed hard disk
    media" regardless of the real type. Keyed by device index; best-effort,
    since this namespace isn't available on every Windows build/edition."""
    media_types = {}
    try:
        import win32com.client

        storage_wmi = win32com.client.GetObject(r"winmgmts:\\.\root\Microsoft\Windows\Storage")
        for disk in storage_wmi.InstancesOf("MSFT_PhysicalDisk"):
            media_types[str(disk.DeviceId)] = _MEDIA_TYPE_NAMES.get(disk.MediaType, "Unknown")
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read disk media types (%s)", exc)
    return media_types


def _disk_details() -> list[dict]:
    disks = []
    media_types = _disk_media_types()
    try:
        wmi = _wmi()
        for disk in wmi.InstancesOf("Win32_DiskDrive"):
            size = getattr(disk, "Size", None)
            index = str(getattr(disk, "Index", ""))
            disks.append(
                {
                    "model": (disk.Model or "").strip(),
                    "size_gb": round(int(size) / (1024**3)) if size else None,
                    "media_type": media_types.get(index, "Unknown"),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read disk details (%s)", exc)
    return disks


def _battery_capacity() -> dict:
    """Design/full-charge capacity live in the root\\WMI namespace, not the
    standard Win32_Battery class — desktops (no battery at all) legitimately
    return nothing here, which is expected, not an error."""
    result = {"battery_design_capacity_mwh": None, "battery_full_charge_capacity_mwh": None}
    try:
        import win32com.client

        wmi_ns = win32com.client.GetObject(r"winmgmts:\\.\root\WMI")
        for static_data in wmi_ns.InstancesOf("BatteryStaticData"):
            result["battery_design_capacity_mwh"] = int(static_data.DesignedCapacity) or None
            break
        for full_charge in wmi_ns.InstancesOf("BatteryFullChargedCapacity"):
            result["battery_full_charge_capacity_mwh"] = int(full_charge.FullChargedCapacity) or None
            break
    except Exception as exc:  # noqa: BLE001 - no battery (desktop) or namespace unavailable
        logger.info("Could not read battery capacity (%s)", exc)
    return result


def gather_hardware_details() -> dict:
    return {
        **_cpu_details(),
        **_motherboard_and_bios(),
        "gpu_details": _gpu_details(),
        "ram_details": _ram_details(),
        "disk_details": _disk_details(),
        **_battery_capacity(),
    }
