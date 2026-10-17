from rest_framework import serializers

from .models import DeviceMetric


class MetricIngestSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True)

    # Only present on the one metrics call the agent sends right after
    # startup (WMI queries for these have real overhead, not worth repeating
    # every 15s) — lets an already-enrolled device pick up the fuller
    # hardware snapshot too, without needing to re-enroll from scratch.
    cpu_cores = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    cpu_threads = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    cpu_speed_mhz = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    motherboard = serializers.CharField(max_length=200, required=False, allow_blank=True)
    bios_version = serializers.CharField(max_length=100, required=False, allow_blank=True)
    gpu_details = serializers.ListField(child=serializers.DictField(), required=False)
    ram_details = serializers.ListField(child=serializers.DictField(), required=False)
    disk_details = serializers.ListField(child=serializers.DictField(), required=False)
    battery_design_capacity_mwh = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    battery_full_charge_capacity_mwh = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    # Also only present on that same once-per-startup call - backfills a
    # device that was enrolled before this data (or the field itself)
    # existed, which otherwise stays stuck blank forever short of a full
    # re-enroll (see agent/src/main.py's main loop for where this is set).
    manufacturer = serializers.CharField(max_length=150, required=False, allow_blank=True)
    model = serializers.CharField(max_length=150, required=False, allow_blank=True)
    system_family = serializers.CharField(max_length=150, required=False, allow_blank=True)
    serial_number = serializers.CharField(max_length=150, required=False, allow_blank=True)

    # Present once an hour (see agent/src/main.py's COMPLIANCE_CHECK_INTERVAL_SECONDS)
    # rather than once ever — unlike hardware specs, these can flip mid-session.
    bitlocker_enabled = serializers.BooleanField(required=False, allow_null=True)
    firewall_enabled = serializers.BooleanField(required=False, allow_null=True)
    antivirus_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    antivirus_enabled = serializers.BooleanField(required=False, allow_null=True)

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
