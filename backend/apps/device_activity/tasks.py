import logging

from celery import shared_task
from django.utils import timezone

from apps.system_settings.models import SystemSettings

from .models import AppUsage, BrowsingHistoryEntry, FileActivityEvent

logger = logging.getLogger("sentineldesk.device_activity")


@shared_task
def prune_old_activity():
    cutoff_days = SystemSettings.get_solo().activity_retention_days
    cutoff = timezone.now() - timezone.timedelta(days=cutoff_days)
    cutoff_date = cutoff.date()

    deleted_app_usage, _ = AppUsage.objects.filter(date__lt=cutoff_date).delete()
    deleted_history, _ = BrowsingHistoryEntry.objects.filter(visited_at__lt=cutoff).delete()
    deleted_files, _ = FileActivityEvent.objects.filter(occurred_at__lt=cutoff).delete()

    total = deleted_app_usage + deleted_history + deleted_files
    if total:
        logger.info(
            "Pruned activity data - app_usage=%s browsing_history=%s file_activity=%s",
            deleted_app_usage,
            deleted_history,
            deleted_files,
        )
    return total
