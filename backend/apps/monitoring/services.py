from django.conf import settings

from apps.devices.models import Device


def evaluate_status(*, cpu_percent, ram_percent, disk_percent, battery_percent, battery_charging):
    """Derives a device status from the latest metric sample. CRITICAL takes
    priority over WARNING; a device with no data breaching any threshold is
    ONLINE (it already sent a metric, so it isn't OFFLINE)."""

    critical = (
        (cpu_percent is not None and cpu_percent >= settings.CPU_CRITICAL_PERCENT)
        or (ram_percent is not None and ram_percent >= settings.RAM_CRITICAL_PERCENT)
        or (disk_percent is not None and disk_percent >= settings.DISK_CRITICAL_PERCENT)
        or (
            battery_percent is not None
            and battery_charging is False
            and battery_percent <= settings.BATTERY_CRITICAL_PERCENT
        )
    )
    if critical:
        return Device.Status.CRITICAL

    warning = (
        (cpu_percent is not None and cpu_percent >= settings.CPU_WARNING_PERCENT)
        or (ram_percent is not None and ram_percent >= settings.RAM_WARNING_PERCENT)
        or (disk_percent is not None and disk_percent >= settings.DISK_WARNING_PERCENT)
    )
    if warning:
        return Device.Status.WARNING

    return Device.Status.ONLINE
