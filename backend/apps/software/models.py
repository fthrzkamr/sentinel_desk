from django.db import models

from apps.devices.models import Device


class Software(models.Model):
    """One installed-program entry on one device. Rows are fully replaced on
    every agent sync (see AgentSoftwareSyncView) so this always reflects the
    device's current install state — uninstalled software simply drops out
    instead of accumulating as history."""

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="software")
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=100, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    install_date = models.DateField(null=True, blank=True)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("device", "name", "version")
        indexes = [
            models.Index(fields=["device", "name"]),
        ]

    def __str__(self):
        return f"{self.name} {self.version} ({self.device.device_id})"
