from django.db import models

from apps.devices.models import Device


class AppUsage(models.Model):
    """Per-device, per-day, per-application accumulated foreground time.
    The agent samples the foreground window every cycle and reports the
    incremental seconds since its last sync — reported deltas are added to
    whatever is already stored, so an agent restart only loses the seconds
    it never got to report, never double-counts."""

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="app_usage")
    app_name = models.CharField(max_length=255)
    window_title = models.CharField(max_length=500, blank=True)
    date = models.DateField()
    duration_seconds = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-duration_seconds"]
        indexes = [models.Index(fields=["device", "-date"])]
        constraints = [
            models.UniqueConstraint(fields=["device", "app_name", "date"], name="unique_app_usage_per_day")
        ]

    def __str__(self):
        return f"{self.device.device_id}:{self.app_name}@{self.date} ({self.duration_seconds}s)"


class BrowsingHistoryEntry(models.Model):
    """One URL visit, synced from the browser's own local history database
    (Chrome/Edge). Deduplicated on (device, url, visited_at) since the agent
    re-scans recent history each cycle rather than tracking a precise
    watermark inside the browser's own timestamp format."""

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="browsing_history")
    browser = models.CharField(max_length=50)
    url = models.CharField(max_length=2000)
    title = models.CharField(max_length=500, blank=True)
    visited_at = models.DateTimeField()

    class Meta:
        ordering = ["-visited_at"]
        indexes = [models.Index(fields=["device", "-visited_at"])]
        constraints = [
            models.UniqueConstraint(fields=["device", "url", "visited_at"], name="unique_history_visit")
        ]

    def __str__(self):
        return f"{self.device.device_id}:{self.browser}:{self.url}"


class FileActivityEvent(models.Model):
    """One filesystem event observed in a watched folder (Desktop, Documents,
    Downloads) on the device — created/modified/deleted/moved. Not a full
    audit of every file on disk, only what happens live while the agent
    is running and watching."""

    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        MODIFIED = "MODIFIED", "Modified"
        DELETED = "DELETED", "Deleted"
        MOVED = "MOVED", "Moved"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="file_activity")
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    path = models.CharField(max_length=1000)
    destination_path = models.CharField(max_length=1000, blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["device", "-occurred_at"])]

    def __str__(self):
        return f"{self.device.device_id}:{self.event_type}:{self.path}"
