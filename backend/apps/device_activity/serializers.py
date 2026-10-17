from rest_framework import serializers

from .models import AppUsage, BrowsingHistoryEntry, FileActivityEvent, IdleActivityStat, SystemErrorEvent


class AppUsageItemSerializer(serializers.Serializer):
    app_name = serializers.CharField(max_length=255)
    window_title = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    date = serializers.DateField()
    duration_seconds = serializers.IntegerField(min_value=0)


class AppUsageIngestSerializer(serializers.Serializer):
    items = AppUsageItemSerializer(many=True)


class AppUsageSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = AppUsage
        fields = ["id", "device_id", "hostname", "app_name", "window_title", "date", "duration_seconds", "last_seen"]
        read_only_fields = fields


class IdleActivityItemSerializer(serializers.Serializer):
    date = serializers.DateField()
    active_seconds = serializers.IntegerField(min_value=0)
    idle_seconds = serializers.IntegerField(min_value=0)


class IdleActivityIngestSerializer(serializers.Serializer):
    items = IdleActivityItemSerializer(many=True)


class IdleActivityStatSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)
    active_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = IdleActivityStat
        fields = ["id", "device_id", "hostname", "date", "active_seconds", "idle_seconds", "active_percent"]
        read_only_fields = fields


class BrowsingHistoryItemSerializer(serializers.Serializer):
    browser = serializers.CharField(max_length=50)
    url = serializers.CharField(max_length=2000)
    title = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    visited_at = serializers.DateTimeField()


class BrowsingHistoryIngestSerializer(serializers.Serializer):
    items = BrowsingHistoryItemSerializer(many=True)


class BrowsingHistorySerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = BrowsingHistoryEntry
        fields = ["id", "device_id", "hostname", "browser", "url", "title", "visited_at"]
        read_only_fields = fields


class FileActivityItemSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=FileActivityEvent.EventType.choices)
    path = serializers.CharField(max_length=1000)
    destination_path = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    source = serializers.ChoiceField(
        choices=FileActivityEvent.Source.choices, required=False, default=FileActivityEvent.Source.LOCAL
    )
    occurred_at = serializers.DateTimeField()


class FileActivityIngestSerializer(serializers.Serializer):
    items = FileActivityItemSerializer(many=True)


class FileActivitySerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = FileActivityEvent
        fields = ["id", "device_id", "hostname", "event_type", "path", "destination_path", "source", "occurred_at"]
        read_only_fields = fields


class SystemErrorItemSerializer(serializers.Serializer):
    log_name = serializers.CharField(max_length=20)
    provider = serializers.CharField(max_length=255)
    event_id = serializers.IntegerField(min_value=0)
    level = serializers.ChoiceField(choices=SystemErrorEvent.Level.choices)
    message = serializers.CharField(required=False, allow_blank=True, default="")
    occurred_at = serializers.DateTimeField()


class SystemErrorIngestSerializer(serializers.Serializer):
    items = SystemErrorItemSerializer(many=True)


class SystemErrorSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = SystemErrorEvent
        fields = ["id", "device_id", "hostname", "log_name", "provider", "event_id", "level", "message", "occurred_at"]
        read_only_fields = fields


class UsbEventSerializer(serializers.Serializer):
    event = serializers.ChoiceField(choices=["connected", "disconnected"])
    label = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    drive_letter = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    serial = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
