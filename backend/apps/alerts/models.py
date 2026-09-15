from django.conf import settings
from django.db import models

from apps.devices.models import Device


class Alert(models.Model):
    """A device condition that crossed a threshold (Phase 3's WARNING/CRITICAL
    logic, plus connectivity). One row tracks the whole lifetime of a single
    ongoing condition — it's created once when the condition starts, reused
    (not duplicated) while it persists, and resolved automatically once the
    condition clears or manually by an admin."""

    class Category(models.TextChoices):
        CPU = "CPU", "CPU Usage"
        RAM = "RAM", "RAM Usage"
        DISK = "DISK", "Disk Usage"
        BATTERY = "BATTERY", "Battery Level"
        CONNECTIVITY = "CONNECTIVITY", "Connectivity"

    class Severity(models.TextChoices):
        WARNING = "WARNING", "Warning"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        RESOLVED = "RESOLVED", "Resolved"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="alerts")
    category = models.CharField(max_length=20, choices=Category.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    message = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)

    triggered_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts_acknowledged",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts_resolved",
    )

    class Meta:
        ordering = ["-triggered_at"]
        indexes = [
            models.Index(fields=["-triggered_at"]),
            models.Index(fields=["device", "category", "status"]),
        ]

    def __str__(self):
        return f"{self.device.device_id}:{self.category}:{self.status}"
