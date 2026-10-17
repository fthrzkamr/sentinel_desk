from django.db import models

from apps.devices.models import Device


class Location(models.Model):
    """One location sample. `latitude`/`longitude`/`accuracy_meters` are all
    nullable — when neither the OS location service nor IP geolocation could
    resolve a position, we still record the attempt (source + timestamp)
    rather than inventing coordinates."""

    class Source(models.TextChoices):
        OS = "OS", "OS Location Service"
        IP = "IP", "IP Geolocation (estimate)"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="locations")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    accuracy_meters = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=2, choices=Source.choices)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["device", "-recorded_at"]),
        ]

    def __str__(self):
        return f"{self.device.device_id} @ {self.recorded_at:%Y-%m-%d %H:%M:%S} ({self.source})"
