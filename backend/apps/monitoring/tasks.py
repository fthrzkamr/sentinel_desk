import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.alerts.services import trigger_connectivity_alert
from apps.devices.models import Device

from .broadcast import broadcast_dashboard_event
from .models import DeviceMetric

logger = logging.getLogger("sentineldesk.monitoring")


@shared_task
def mark_stale_devices_offline():
    """Runs periodically (see CELERY_BEAT_SCHEDULE). A device is OFFLINE once
    its last heartbeat/metric is older than DEVICE_OFFLINE_THRESHOLD_SECONDS —
    this is the only place that transitions a device TO offline."""

    cutoff = timezone.now() - timezone.timedelta(seconds=settings.DEVICE_OFFLINE_THRESHOLD_SECONDS)
    stale_devices = Device.objects.filter(last_seen__lt=cutoff).exclude(
        status__in=[Device.Status.OFFLINE, Device.Status.DISABLED]
    )

    count = 0
    for device in stale_devices:
        device.status = Device.Status.OFFLINE
        device.save(update_fields=["status"])
        broadcast_dashboard_event(
            "device.status_changed",
            {"device_id": device.device_id, "status": device.status, "last_seen": device.last_seen.isoformat()},
        )
        alert = trigger_connectivity_alert(device)
        if alert:
            broadcast_dashboard_event(
                "alert.triggered",
                {
                    "id": alert.id,
                    "device_id": device.device_id,
                    "category": alert.category,
                    "severity": alert.severity,
                    "message": alert.message,
                },
            )
        count += 1

    if count:
        logger.info("Marked %s device(s) OFFLINE", count)
    return count


@shared_task
def prune_old_metrics():
    cutoff = timezone.now() - timezone.timedelta(days=settings.DEVICE_METRIC_RETENTION_DAYS)
    deleted, _ = DeviceMetric.objects.filter(recorded_at__lt=cutoff).delete()
    if deleted:
        logger.info("Pruned %s old metric row(s)", deleted)
    return deleted
