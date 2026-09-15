from rest_framework import serializers

from .models import DeviceMetric


class MetricIngestSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True)

    cpu_percent = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=100)
    cpu_frequency_mhz = serializers.FloatField(required=False, allow_null=True, min_value=0)

    ram_total_mb = serializers.FloatField(required=False, allow_null=True, min_value=0)
    ram_used_mb = serializers.FloatField(required=False, allow_null=True, min_value=0)
    ram_percent = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=100)

    disk_total_gb = serializers.FloatField(required=False, allow_null=True, min_value=0)
    disk_used_gb = serializers.FloatField(required=False, allow_null=True, min_value=0)
    disk_free_gb = serializers.FloatField(required=False, allow_null=True, min_value=0)
    disk_percent = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=100)

    net_upload_kbps = serializers.FloatField(required=False, allow_null=True, min_value=0)
    net_download_kbps = serializers.FloatField(required=False, allow_null=True, min_value=0)

    battery_percent = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=100)
    battery_charging = serializers.BooleanField(required=False, allow_null=True)

    uptime_seconds = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class DeviceMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceMetric
        fields = [
            "id",
            "recorded_at",
            "cpu_percent",
            "cpu_frequency_mhz",
            "ram_total_mb",
            "ram_used_mb",
            "ram_percent",
            "disk_total_gb",
            "disk_used_gb",
            "disk_free_gb",
            "disk_percent",
            "net_upload_kbps",
            "net_download_kbps",
            "battery_percent",
            "battery_charging",
            "uptime_seconds",
        ]
        read_only_fields = fields
