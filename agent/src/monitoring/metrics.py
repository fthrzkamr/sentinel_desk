"""Realtime metric sampling (CPU/RAM/disk/network/battery usage right now) —
sent every MONITOR_INTERVAL seconds. Distinct from system_info.py, which only
captures a one-time snapshot of what the machine is at enrollment time."""

import platform
import time

import psutil


class MetricsCollector:
    def __init__(self):
        self._last_net = psutil.net_io_counters()
        self._last_time = time.monotonic()
        # Prime psutil's internal CPU sample so the first real reading isn't 0.0.
        psutil.cpu_percent(interval=None)

    def collect(self) -> dict:
        now = time.monotonic()
        elapsed = max(now - self._last_time, 0.001)

        net = psutil.net_io_counters()
        upload_kbps = (net.bytes_sent - self._last_net.bytes_sent) * 8 / 1000 / elapsed
        download_kbps = (net.bytes_recv - self._last_net.bytes_recv) * 8 / 1000 / elapsed
        self._last_net = net
        self._last_time = now

        virtual_memory = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")

        cpu_freq = psutil.cpu_freq()
        battery = psutil.sensors_battery()

        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cpu_frequency_mhz": cpu_freq.current if cpu_freq else None,
            "ram_total_mb": round(virtual_memory.total / (1024**2), 1),
            "ram_used_mb": round(virtual_memory.used / (1024**2), 1),
            "ram_percent": virtual_memory.percent,
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_percent": disk.percent,
            "net_upload_kbps": round(max(upload_kbps, 0), 2),
            "net_download_kbps": round(max(download_kbps, 0), 2),
            "battery_percent": battery.percent if battery else None,
            "battery_charging": battery.power_plugged if battery else None,
            "uptime_seconds": int(time.time() - psutil.boot_time()),
        }
