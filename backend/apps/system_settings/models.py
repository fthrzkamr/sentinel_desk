from django.conf import settings
from django.core.cache import cache
from django.db import models

CACHE_KEY = "system_settings:solo"
CACHE_TTL_SECONDS = 300


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
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

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
            },
        )
        cache.set(CACHE_KEY, obj, timeout=CACHE_TTL_SECONDS)
        return obj
