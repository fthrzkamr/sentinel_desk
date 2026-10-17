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


class IdleActivityStat(models.Model):
    """Per-device, per-day active-vs-idle seconds — the same accumulate-a-
    delta-each-sync pattern as AppUsage. "Active" means the system-wide
    GetLastInputInfo timestamp moved during that interval (a mouse/keyboard
    event happened somewhere), never what was typed or clicked."""

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="idle_activity")
    date = models.DateField()
    active_seconds = models.PositiveIntegerField(default=0)
    idle_seconds = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        indexes = [models.Index(fields=["device", "-date"])]
        constraints = [
            models.UniqueConstraint(fields=["device", "date"], name="unique_idle_activity_per_day")
        ]

    def __str__(self):
        return f"{self.device.device_id}:{self.date} (active={self.active_seconds}s idle={self.idle_seconds}s)"

    @property
    def active_percent(self) -> float | None:
        total = self.active_seconds + self.idle_seconds
        if total == 0:
            return None
        return round(self.active_seconds / total * 100, 1)


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

    class Source(models.TextChoices):
        LOCAL = "LOCAL", "Local folder (Desktop/Documents/Downloads)"
        USB = "USB", "Removable media"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="file_activity")
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    path = models.CharField(max_length=1000)
    destination_path = models.CharField(max_length=1000, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.LOCAL)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["device", "-occurred_at"])]

    def __str__(self):
        return f"{self.device.device_id}:{self.event_type}:{self.path}"


class SystemErrorEvent(models.Model):
    """One Error/Critical-level entry read from the device's own local
    Windows Event Log (System + Application channels) — driver crashes,
    hardware failures, unexpected shutdowns, application crashes. Lets IT
    diagnose a device remotely from its actual event history instead of
    needing physical/RDP access just to open Event Viewer."""

    class Level(models.TextChoices):
        ERROR = "ERROR", "Error"
        CRITICAL = "CRITICAL", "Critical"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="system_errors")
    log_name = models.CharField(max_length=20)  # "System" or "Application"
    provider = models.CharField(max_length=255)  # e.g. "Disk", "nvlddmkm", "Kernel-Power"
    event_id = models.PositiveIntegerField()
    level = models.CharField(max_length=10, choices=Level.choices)
    message = models.TextField(blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["device", "-occurred_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["device", "log_name", "provider", "event_id", "occurred_at"],
                name="unique_system_error_event",
            )
        ]

    def __str__(self):
        return f"{self.device.device_id}:{self.log_name}:{self.provider}:{self.event_id}"
