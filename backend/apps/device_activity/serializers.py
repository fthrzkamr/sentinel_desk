from rest_framework import serializers

from .models import AppUsage, BrowsingHistoryEntry, FileActivityEvent


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
    occurred_at = serializers.DateTimeField()


class FileActivityIngestSerializer(serializers.Serializer):
    items = FileActivityItemSerializer(many=True)


class FileActivitySerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = FileActivityEvent
        fields = ["id", "device_id", "hostname", "event_type", "path", "destination_path", "occurred_at"]
        read_only_fields = fields


class UsbEventSerializer(serializers.Serializer):
    event = serializers.ChoiceField(choices=["connected", "disconnected"])
    label = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    drive_letter = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    serial = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
