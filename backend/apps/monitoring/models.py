from django.db import models

from apps.devices.models import Device


class DeviceMetric(models.Model):
    """Raw realtime metric sample. Short retention by design (see
    DEVICE_METRIC_RETENTION_DAYS) — aggregated/long-term history is a later
    phase concern, not stored here."""

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="metrics")
    recorded_at = models.DateTimeField(auto_now_add=True)

    cpu_percent = models.FloatField(null=True, blank=True)
    cpu_frequency_mhz = models.FloatField(null=True, blank=True)

    ram_total_mb = models.FloatField(null=True, blank=True)
    ram_used_mb = models.FloatField(null=True, blank=True)
    ram_percent = models.FloatField(null=True, blank=True)

    disk_total_gb = models.FloatField(null=True, blank=True)
    disk_used_gb = models.FloatField(null=True, blank=True)
    disk_free_gb = models.FloatField(null=True, blank=True)
    disk_percent = models.FloatField(null=True, blank=True)

    net_upload_kbps = models.FloatField(null=True, blank=True)
    net_download_kbps = models.FloatField(null=True, blank=True)

    battery_percent = models.FloatField(null=True, blank=True)
    battery_charging = models.BooleanField(null=True, blank=True)

    uptime_seconds = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["device", "-recorded_at"]),
        ]

    def __str__(self):
        return f"{self.device.device_id} @ {self.recorded_at:%Y-%m-%d %H:%M:%S}"
