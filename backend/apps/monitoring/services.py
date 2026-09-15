from apps.devices.models import Device
from apps.system_settings.models import SystemSettings


def evaluate_status(*, cpu_percent, ram_percent, disk_percent, battery_percent, battery_charging):
    """Derives a device status from the latest metric sample. CRITICAL takes
    priority over WARNING; a device with no data breaching any threshold is
    ONLINE (it already sent a metric, so it isn't OFFLINE)."""

    config = SystemSettings.get_solo()

    critical = (
        (cpu_percent is not None and cpu_percent >= config.cpu_critical_percent)
        or (ram_percent is not None and ram_percent >= config.ram_critical_percent)
        or (disk_percent is not None and disk_percent >= config.disk_critical_percent)
        or (
            battery_percent is not None
            and battery_charging is False
            and battery_percent <= config.battery_critical_percent
        )
    )
    if critical:
        return Device.Status.CRITICAL

    warning = (
        (cpu_percent is not None and cpu_percent >= config.cpu_warning_percent)
        or (ram_percent is not None and ram_percent >= config.ram_warning_percent)
        or (disk_percent is not None and disk_percent >= config.disk_warning_percent)
    )
    if warning:
        return Device.Status.WARNING

    return Device.Status.ONLINE
