from django.conf import settings
from django.core.cache import cache
from django.db import models

CACHE_KEY = "system_settings:solo"
CACHE_TTL_SECONDS = 300

# Every non-pk, non-auto field get_solo() needs to survive a cache round-trip
# on its own — see the comment on get_solo() for why these are cached as a
# plain dict rather than the model instance itself.
_CACHED_FIELDS = [
    "cpu_warning_percent",
    "cpu_critical_percent",
    "ram_warning_percent",
    "ram_critical_percent",
    "disk_warning_percent",
    "disk_critical_percent",
    "battery_critical_percent",
    "device_offline_threshold_seconds",
    "device_metric_retention_days",
    "activity_retention_days",
    "data_exfil_min_local_files",
    "work_hours_start",
    "work_hours_end",
    "notifications_enabled",
    "telegram_bot_token",
    "telegram_chat_id",
    "webhook_url",
    "notification_emails",
    # Dynamic Agent Remote Policy (Tahap 4)
    "agent_metrics_interval_seconds",
    "agent_screen_monitor_enabled",
    "agent_usb_monitor_enabled",
    "agent_app_usage_monitor_enabled",
    "agent_browser_history_monitor_enabled",
    "agent_file_activity_monitor_enabled",
    "agent_idle_activity_monitor_enabled",
    "agent_system_error_monitor_enabled",
    # Over-The-Air (OTA) Agent Auto-Update (Tahap 4)
    "agent_auto_update_enabled",
    "agent_latest_version",
    "agent_download_url",
    "agent_sha256",
    # Live Screen WebRTC ICE / TURN Configuration (Tahap 5)
    "stun_server_url",
    "turn_server_enabled",
    "turn_server_url",
    "turn_username",
    "turn_credential",
    # Data Retention Policies (Tahap 6)
    "alert_retention_days",
    "audit_retention_days",
]


class SystemSettings(models.Model):
    """Single-row table (always pk=1) for the operational thresholds that
    used to be env-var-only (CPU_WARNING_PERCENT etc. in config/settings) —
    admins change these often enough in practice that requiring an env edit
    plus a full container restart was the wrong tradeoff. Everything that
    used to read `django.conf.settings.X` for one of these now reads
    `SystemSettings.get_solo()` instead; the original env vars remain as the
    seed values the very first row is created with, and as the fallback
    `config/settings/base.py` still exposes for anything not yet migrated."""

    cpu_warning_percent = models.FloatField(default=80)
    cpu_critical_percent = models.FloatField(default=95)
    ram_warning_percent = models.FloatField(default=80)
    ram_critical_percent = models.FloatField(default=95)
    disk_warning_percent = models.FloatField(default=85)
    disk_critical_percent = models.FloatField(default=95)
    battery_critical_percent = models.FloatField(default=10)
    device_offline_threshold_seconds = models.PositiveIntegerField(default=60)
    device_metric_retention_days = models.PositiveIntegerField(default=7)
    # App usage/browsing history/file activity are far lower-volume than raw
    # metric samples (one row per app-per-day, or per real visit/file event —
    # not one per heartbeat), so a longer default retention than metrics is
    # fine without the table growing out of control.
    activity_retention_days = models.PositiveIntegerField(default=180)
    # Local hour-of-day (0-23, DJANGO_TIME_ZONE) bounding normal work hours —
    # any app usage/browsing/file activity outside this window raises an
    # OUT_OF_HOURS alert. work_hours_end may be less than work_hours_start
    # to express an overnight-inclusive window; that's intentionally not
    # validated here since some shifts genuinely span midnight.
    work_hours_start = models.PositiveSmallIntegerField(default=8)
    work_hours_end = models.PositiveSmallIntegerField(default=18)
    # How many local files must have been created/modified in the 10
    # minutes before a file-sharing-site visit before that visit is worth
    # a DATA_EXFIL alert at all - see trigger_cloud_upload_alert. 1 fires
    # on completely ordinary behavior (edit a doc, upload it to the
    # company's own Drive) that every employee does routinely; at a
    # fleet's real scale (dozens of laptops, each doing this daily) that
    # reads as spam rather than a signal. A deliberate jump in activity
    # (several files right before a cloud visit) is a meaningfully
    # stronger signal than "touched one file, then opened Drive."
    data_exfil_min_local_files = models.PositiveSmallIntegerField(default=2)

    # External notification channels for CRITICAL alerts (Tahap 2).
    notifications_enabled = models.BooleanField(default=False)
    telegram_bot_token = models.CharField(max_length=200, blank=True, default="")
    telegram_chat_id = models.CharField(max_length=100, blank=True, default="")
    webhook_url = models.URLField(max_length=500, blank=True, default="")
    notification_emails = models.CharField(max_length=500, blank=True, default="")

    # Dynamic Agent Remote Policy (Tahap 4)
    agent_metrics_interval_seconds = models.PositiveIntegerField(default=15)
    agent_screen_monitor_enabled = models.BooleanField(default=True)
    agent_usb_monitor_enabled = models.BooleanField(default=True)
    agent_app_usage_monitor_enabled = models.BooleanField(default=True)
    agent_browser_history_monitor_enabled = models.BooleanField(default=True)
    agent_file_activity_monitor_enabled = models.BooleanField(default=True)
    agent_idle_activity_monitor_enabled = models.BooleanField(default=True)
    agent_system_error_monitor_enabled = models.BooleanField(default=True)

    # Over-The-Air (OTA) Agent Auto-Update (Tahap 4)
    agent_auto_update_enabled = models.BooleanField(default=False)
    agent_latest_version = models.CharField(max_length=50, blank=True, default="")
    agent_download_url = models.CharField(max_length=500, blank=True, default="")
    agent_sha256 = models.CharField(max_length=64, blank=True, default="")

    # Live Screen WebRTC ICE / TURN Configuration (Tahap 5)
    stun_server_url = models.CharField(max_length=255, blank=True, default="stun:stun.l.google.com:19302")
    turn_server_enabled = models.BooleanField(default=False)
    turn_server_url = models.CharField(max_length=255, blank=True, default="")
    turn_username = models.CharField(max_length=150, blank=True, default="")
    turn_credential = models.CharField(max_length=150, blank=True, default="")

    # Data Retention Policies (Tahap 6)
    alert_retention_days = models.PositiveIntegerField(default=60)
    audit_retention_days = models.PositiveIntegerField(default=180)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "System Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    @classmethod
    def get_solo(cls) -> "SystemSettings":
        # Caches a plain {field: value} dict rather than the model instance
        # itself. Caching the instance directly is fragile across a Redis
        # round-trip: a value fetched via cache.get() right after another
        # call's get_or_create()/save() can come back as a *deferred*
        # instance (missing fields from __dict__ depending on exactly how it
        # was constructed), and accessing a deferred field transparently
        # tries to refresh_from_db() — which raises DoesNotExist if that
        # happens inside a test's transaction after the row was rolled back,
        # or more subtly any time the cached copy and the DB briefly
        # disagree. A plain dict has no such lazy-loading behavior.
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cls(pk=1, **cached)

        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "cpu_warning_percent": settings.CPU_WARNING_PERCENT,
                "cpu_critical_percent": settings.CPU_CRITICAL_PERCENT,
                "ram_warning_percent": settings.RAM_WARNING_PERCENT,
                "ram_critical_percent": settings.RAM_CRITICAL_PERCENT,
                "disk_warning_percent": settings.DISK_WARNING_PERCENT,
                "disk_critical_percent": settings.DISK_CRITICAL_PERCENT,
                "battery_critical_percent": settings.BATTERY_CRITICAL_PERCENT,
                "device_offline_threshold_seconds": settings.DEVICE_OFFLINE_THRESHOLD_SECONDS,
                "device_metric_retention_days": settings.DEVICE_METRIC_RETENTION_DAYS,
                "activity_retention_days": settings.ACTIVITY_RETENTION_DAYS,
                "data_exfil_min_local_files": settings.DATA_EXFIL_MIN_LOCAL_FILES,
                "work_hours_start": settings.WORK_HOURS_START,
                "work_hours_end": settings.WORK_HOURS_END,
                "agent_metrics_interval_seconds": 15,
                "agent_screen_monitor_enabled": True,
                "agent_usb_monitor_enabled": True,
                "agent_app_usage_monitor_enabled": True,
                "agent_browser_history_monitor_enabled": True,
                "agent_file_activity_monitor_enabled": True,
                "agent_idle_activity_monitor_enabled": True,
                "agent_system_error_monitor_enabled": True,
                "agent_auto_update_enabled": False,
                "agent_latest_version": "",
                "agent_download_url": "",
                "agent_sha256": "",
                "stun_server_url": "stun:stun.l.google.com:19302",
                "turn_server_enabled": False,
                "turn_server_url": "",
                "turn_username": "",
                "turn_credential": "",
                "alert_retention_days": 60,
                "audit_retention_days": 180,
            },
        )
        cache.set(CACHE_KEY, {field: getattr(obj, field) for field in _CACHED_FIELDS}, timeout=CACHE_TTL_SECONDS)
        return obj
