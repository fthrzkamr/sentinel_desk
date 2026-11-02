from django.utils import timezone

from apps.system_settings.models import SystemSettings

from .models import Alert
from .tasks import enqueue_critical_alert_notification

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
        escalated_to_critical = (
            existing.severity != Alert.Severity.CRITICAL and severity == Alert.Severity.CRITICAL
        )
        if existing.severity != severity or existing.message != message:
            existing.severity = severity
            existing.message = message
            existing.metadata = metadata
            existing.save(update_fields=["severity", "message", "metadata"])
        if escalated_to_critical:
            enqueue_critical_alert_notification(existing)
        return existing, False
    alert = Alert.objects.create(
        device=device, category=category, severity=severity, message=message, metadata=metadata
    )
    if severity == Alert.Severity.CRITICAL:
        enqueue_critical_alert_notification(alert)
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


def trigger_usb_alert(device, *, label, drive_letter, serial):
    alert, created = _trigger(
        device,
        Alert.Category.USB,
        Alert.Severity.WARNING,
        f"Media eksternal terhubung: {label or drive_letter} ({drive_letter})",
        {"label": label, "drive_letter": drive_letter, "serial": serial},
    )
    return alert if created else None


def resolve_usb_alert(device):
    return _auto_resolve(device, Alert.Category.USB, "media_removed")


def check_out_of_hours_activity(device, activity_timestamp, description: str):
    """Flags app usage/browsing/file activity whose local clock hour falls
    outside SystemSettings.work_hours_start/end. One open alert per device
    is reused (like every other alert here) — each new out-of-hours event
    just refreshes its message/metadata to the latest occurrence rather
    than spawning a duplicate for every single event in a burst."""
    config = SystemSettings.get_solo()
    local_time = timezone.localtime(activity_timestamp)
    hour = local_time.hour

    start, end = config.work_hours_start, config.work_hours_end
    within_hours = start <= hour < end if start < end else (hour >= start or hour < end)
    if within_hours:
        return None

    alert, created = _trigger(
        device,
        Alert.Category.OUT_OF_HOURS,
        Alert.Severity.WARNING,
        f"Aktivitas di luar jam kerja ({local_time.strftime('%H:%M')}): {description}",
        {"detected_at": local_time.isoformat(), "description": description},
    )
    return alert if created else None


def trigger_new_software_alert(device, *, names: list[str], unauthorized: bool = False):
    """Flags software that showed up between two inventory syncs — visibility
    only (SentinelDesk observes, it doesn't block installs at the OS level).
    Like the USB/data-exfil alerts, a burst of installs in one sync collapses
    into a single reused alert listing every new name, instead of one alert
    per app.

    `unauthorized=True` means a software whitelist is configured (see
    apps.software.models.SoftwareWhitelistEntry) and none of these names are
    on it — escalated to CRITICAL instead of the default WARNING."""
    joined = ", ".join(names)
    severity = Alert.Severity.CRITICAL if unauthorized else Alert.Severity.WARNING
    prefix = "Software TIDAK di whitelist terdeteksi" if unauthorized else "Software baru terdeteksi"
    alert, created = _trigger(
        device,
        Alert.Category.NEW_SOFTWARE,
        severity,
        f"{prefix}: {joined}",
        {"names": names, "unauthorized": unauthorized},
    )
    return alert if created else None


# Per-occurrence point value within the scoring window, keyed by category —
# picked to roughly reflect insider-threat severity (data exfil >> a stray
# out-of-hours login), not measured/calibrated against real incident data.
# Deliberately excludes CPU/RAM/Disk/Battery/Connectivity: those are hardware
# performance signals, not behavior — a laptop with a slow CPU shouldn't
# score as a bigger insider-threat risk than one that never trips a metric
# alert at all.
RISK_CATEGORY_WEIGHTS = {
    Alert.Category.DATA_EXFIL: 25,
    Alert.Category.SUSPICIOUS_URL: 15,
    Alert.Category.USB: 10,
    Alert.Category.OUT_OF_HOURS: 8,
    Alert.Category.NEW_SOFTWARE: 5,
}
# SYSTEM_ERROR deliberately excluded from RISK_CATEGORY_WEIGHTS — like
# CPU/RAM/Disk/Battery/Connectivity, it's a hardware/reliability signal, not
# a behavioral one, so it shouldn't move an insider-threat score.
RISK_WINDOW_DAYS = 30
RISK_OPEN_MULTIPLIER = 1.5  # still-unresolved alerts weigh more than ones already closed out
RISK_MAX_SCORE = 100


def compute_risk_score(device, *, window_days: int = RISK_WINDOW_DAYS) -> dict:
    """A single 0-100 "how much does this device's recent alert history look
    like insider-threat behavior" number, computed entirely from alerts
    already on record — no new data collection. Meant as a triage signal
    (which device to look at first), not a verdict; the breakdown is
    returned alongside the score so an admin can see exactly why."""
    since = timezone.now() - timezone.timedelta(days=window_days)
    alerts = device.alerts.filter(triggered_at__gte=since)

    breakdown = []
    total = 0
    for category, weight in RISK_CATEGORY_WEIGHTS.items():
        category_alerts = [a for a in alerts if a.category == category]
        if not category_alerts:
            continue
        points = sum(weight * RISK_OPEN_MULTIPLIER if a.status != Alert.Status.RESOLVED else weight for a in category_alerts)
        total += points
        breakdown.append(
            {
                "category": category,
                "count": len(category_alerts),
                "unresolved_count": sum(1 for a in category_alerts if a.status != Alert.Status.RESOLVED),
                "points": round(points, 1),
            }
        )

    breakdown.sort(key=lambda row: row["points"], reverse=True)
    score = min(RISK_MAX_SCORE, round(total))

    if score >= 70:
        level = "HIGH"
    elif score >= 35:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {"score": score, "level": level, "window_days": window_days, "breakdown": breakdown}


def trigger_data_exfil_alert(device, *, drive_letter, event_type, path):
    alert, created = _trigger(
        device,
        Alert.Category.DATA_EXFIL,
        Alert.Severity.CRITICAL,
        f"Kemungkinan kebocoran data: file {event_type.lower()} ke media eksternal {drive_letter} ({path})",
        {"drive_letter": drive_letter, "event_type": event_type, "path": path},
    )
    return alert if created else None


# Visiting one of these is a second data-exfiltration vector the USB-copy
# check above can't see at all (uploading to personal cloud storage instead
# of copying to a USB drive) — deliberately includes "legitimate" services
# like Google Drive/OneDrive too, since this can't tell a personal account
# apart from a corporate one, and a personal account is exactly the risk.
FILE_SHARING_DOMAINS = [
    "drive.google.com",
    "dropbox.com",
    "wetransfer.com",
    "mega.nz",
    "box.com",
    "mediafire.com",
    "1drv.ms",
    "onedrive.live.com",
]


def trigger_cloud_upload_alert(device, *, url, recent_local_file_count: int):
    """Shares the DATA_EXFIL category with trigger_data_exfil_alert on
    purpose — both are the same underlying concern (data leaving the
    company), just a different vector, and _trigger's per-(device,category)
    dedup means firing both close together collapses into one alert instead
    of two, which is the correct behavior here.

    Only fires once recent_local_file_count clears SystemSettings'
    data_exfil_min_local_files (default 2) - a visit to Drive/Dropbox/etc
    with no (or just one) recently-created-or-modified local file behind
    it is indistinguishable from completely ordinary daily use of a
    file-sharing site a company actually relies on (editing a doc then
    uploading it, browsing an existing shared folder, ...). At real fleet
    scale this matters a lot more than it looks in a one-laptop test:
    every employee doing that one routine action once a day would each
    trip a CRITICAL "possible data leak" alert, which reads as spam
    rather than signal once there are dozens of them. A deliberate burst
    of several files right before a cloud visit is a meaningfully
    stronger signal than touching one file and then opening Drive."""
    threshold = SystemSettings.get_solo().data_exfil_min_local_files
    if recent_local_file_count < threshold:
        return None
    severity = Alert.Severity.CRITICAL
    detail = f", {recent_local_file_count} file lokal baru diubah dalam 10 menit terakhir"
    alert, created = _trigger(
        device,
        Alert.Category.DATA_EXFIL,
        severity,
        f"Kemungkinan kebocoran data: kunjungan ke situs file-sharing ({url[:80]}){detail}",
        {"url": url, "vector": "cloud_upload", "recent_local_file_count": recent_local_file_count},
    )
    return alert if created else None


def trigger_suspicious_url_alert(device, *, url, title, reasons: list[str]):
    """`reasons` comes from url_analysis.classify_url() — 2+ stacked signals
    is a much stronger phishing indicator than any single one alone, so it
    escalates to CRITICAL the same way trigger_new_software_alert escalates
    on unauthorized=True."""
    severity = Alert.Severity.CRITICAL if len(reasons) >= 2 else Alert.Severity.WARNING
    alert, created = _trigger(
        device,
        Alert.Category.SUSPICIOUS_URL,
        severity,
        f"URL mencurigakan dikunjungi: {url[:100]} ({', '.join(reasons)})",
        {"url": url, "title": title, "reasons": reasons},
    )
    return alert if created else None


def trigger_system_error_alert(device, *, provider, event_id, message):
    """Only CRITICAL-level Event Log entries raise an alert — Error-level
    ones are still stored (see SystemErrorEvent) for browsing/history, but
    alerting on every one of those would be noisy (some apps log routine
    Error-level entries fairly often); Critical is reserved for things like
    unexpected shutdowns, disk failure warnings, and driver crashes."""
    alert, created = _trigger(
        device,
        Alert.Category.SYSTEM_ERROR,
        Alert.Severity.CRITICAL,
        f"Error sistem kritis: {provider} (Event ID {event_id}) — {message[:150]}",
        {"provider": provider, "event_id": event_id, "message": message},
    )
    return alert if created else None
