import logging

from celery import shared_task

from django.utils import timezone

from apps.audit.models import AuditLog
from apps.system_settings.models import SystemSettings

from .models import Alert
from .notifications import dispatch_notification, format_alert_notification, has_any_channel_configured

logger = logging.getLogger("sentineldesk.alerts")


@shared_task
def prune_old_resolved_alerts():
    retention_days = SystemSettings.get_solo().alert_retention_days
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    deleted, _ = Alert.objects.filter(status=Alert.Status.RESOLVED, resolved_at__lt=cutoff).delete()
    if deleted:
        logger.info("Pruned %s old resolved alert(s) older than %s days", deleted, retention_days)
    return deleted


@shared_task
def prune_old_audit_logs():
    retention_days = SystemSettings.get_solo().audit_retention_days
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    deleted, _ = AuditLog.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("Pruned %s old audit log(s) older than %s days", deleted, retention_days)
    return deleted


@shared_task
def send_critical_alert_notification_task(alert_id: int) -> dict:
    config = SystemSettings.get_solo()
    if not config.notifications_enabled or not has_any_channel_configured(config):
        return {"sent": [], "errors": {}, "skipped": True}

    alert = (
        Alert.objects.select_related("device", "device__assigned_employee", "device__branch")
        .filter(pk=alert_id)
        .first()
    )
    if not alert:
        return {"sent": [], "errors": {}, "skipped": True}

    title, body, meta = format_alert_notification(alert)
    result = dispatch_notification(title=title, body=body, metadata=meta, config=config)
    if result["sent"]:
        logger.info("Sent critical alert #%s notification via %s", alert_id, ", ".join(result["sent"]))
    return result


def enqueue_critical_alert_notification(alert: Alert) -> None:
    """Queues `send_critical_alert_notification_task` when external
    notifications are enabled. Wrapped so a broker outage never blocks alert
    creation or agent ingestion."""
    try:
        config = SystemSettings.get_solo()
        if not config.notifications_enabled or not has_any_channel_configured(config):
            return
        send_critical_alert_notification_task.delay(alert.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not enqueue critical alert notification for alert #%s: %s", alert.id, exc)

