from django.utils import timezone

from apps.system_settings.models import SystemSettings

from .models import Alert

_OPEN_STATUSES = [Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED]

_METRIC_CHECKS = [
    (Alert.Category.CPU, "cpu_percent", "cpu_warning_percent", "cpu_critical_percent", "CPU usage"),
    (Alert.Category.RAM, "ram_percent", "ram_warning_percent", "ram_critical_percent", "RAM usage"),
    (Alert.Category.DISK, "disk_percent", "disk_warning_percent", "disk_critical_percent", "Disk usage"),
]


def _open_alert(device, category):
    return Alert.objects.filter(device=device, category=category, status__in=_OPEN_STATUSES).first()


def _trigger(device, category, severity, message, metadata):
    """Reuses an already-open alert for this (device, category) instead of
    creating a duplicate for every metric sample the condition persists
    through — an admin acknowledging an alert shouldn't have it reappear on
    the next heartbeat while nothing has actually changed."""
    existing = _open_alert(device, category)
    if existing:
        if existing.severity != severity or existing.message != message:
            existing.severity = severity
            existing.message = message
            existing.metadata = metadata
            existing.save(update_fields=["severity", "message", "metadata"])
        return existing, False
    alert = Alert.objects.create(
        device=device, category=category, severity=severity, message=message, metadata=metadata
    )
    return alert, True


def _auto_resolve(device, category, reason):
    existing = _open_alert(device, category)
    if not existing:
        return None
    existing.status = Alert.Status.RESOLVED
    existing.resolved_at = timezone.now()
    existing.metadata = {**existing.metadata, "resolution": reason}
    existing.save(update_fields=["status", "resolved_at", "metadata"])
    return existing


def sync_metric_alerts(device, *, cpu_percent, ram_percent, disk_percent, battery_percent, battery_charging):
    """Mirrors the same thresholds `monitoring.services.evaluate_status` uses
    for the overall device status, but per-metric — so an alert always says
    exactly which metric tripped, and clears the moment that specific metric
    is back under its warning threshold. Returns (triggered, resolved) lists."""

    config = SystemSettings.get_solo()
    values = {"cpu_percent": cpu_percent, "ram_percent": ram_percent, "disk_percent": disk_percent}
    triggered, resolved = [], []

    for category, field, warn_setting, crit_setting, label in _METRIC_CHECKS:
        value = values[field]
        if value is None:
            continue
        warn_th = getattr(config, warn_setting)
        crit_th = getattr(config, crit_setting)

        if value >= crit_th:
            alert, created = _trigger(
                device,
                category,
                Alert.Severity.CRITICAL,
                f"{label} at {value:.0f}% (critical, threshold {crit_th:.0f}%)",
                {"value": value, "threshold": crit_th},
            )
            if created:
                triggered.append(alert)
        elif value >= warn_th:
            alert, created = _trigger(
                device,
                category,
                Alert.Severity.WARNING,
                f"{label} at {value:.0f}% (warning, threshold {warn_th:.0f}%)",
                {"value": value, "threshold": warn_th},
            )
            if created:
                triggered.append(alert)
        else:
            resolved_alert = _auto_resolve(device, category, "back_to_normal")
            if resolved_alert:
                resolved.append(resolved_alert)

    if battery_percent is not None and battery_charging is False and battery_percent <= config.battery_critical_percent:
        alert, created = _trigger(
            device,
            Alert.Category.BATTERY,
            Alert.Severity.CRITICAL,
            f"Battery at {battery_percent:.0f}% and not charging",
            {"value": battery_percent, "threshold": config.battery_critical_percent},
        )
        if created:
            triggered.append(alert)
    else:
        resolved_alert = _auto_resolve(device, Alert.Category.BATTERY, "charging_or_normal")
        if resolved_alert:
            resolved.append(resolved_alert)

    return triggered, resolved


def trigger_connectivity_alert(device):
    alert, created = _trigger(
        device,
        Alert.Category.CONNECTIVITY,
        Alert.Severity.WARNING,
        f"{device.device_id} went offline",
        {},
    )
    return alert if created else None


def resolve_connectivity_alert(device):
    return _auto_resolve(device, Alert.Category.CONNECTIVITY, "device_back_online")
