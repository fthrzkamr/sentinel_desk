from rest_framework import serializers

from .models import SystemSettings


class SystemSettingsSerializer(serializers.ModelSerializer):
    cpu_warning_percent = serializers.FloatField(min_value=0, max_value=100)
    cpu_critical_percent = serializers.FloatField(min_value=0, max_value=100)
    ram_warning_percent = serializers.FloatField(min_value=0, max_value=100)
    ram_critical_percent = serializers.FloatField(min_value=0, max_value=100)
    disk_warning_percent = serializers.FloatField(min_value=0, max_value=100)
    disk_critical_percent = serializers.FloatField(min_value=0, max_value=100)
    battery_critical_percent = serializers.FloatField(min_value=0, max_value=100)
    work_hours_start = serializers.IntegerField(min_value=0, max_value=23)
    work_hours_end = serializers.IntegerField(min_value=0, max_value=23)

    class Meta:
        model = SystemSettings
        fields = [
            "cpu_warning_percent",
            "cpu_critical_percent",
            "ram_warning_percent",
            "ram_critical_percent",
            "disk_warning_percent",
            "disk_critical_percent",
            "battery_critical_percent",
            "device_offline_threshold_seconds",
            "device_metric_retention_days",
            "activity_retention_days",
            "work_hours_start",
            "work_hours_end",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        pairs = [
            ("cpu_warning_percent", "cpu_critical_percent"),
            ("ram_warning_percent", "ram_critical_percent"),
            ("disk_warning_percent", "disk_critical_percent"),
        ]
        for warn_field, crit_field in pairs:
            warn_value = attrs.get(warn_field, getattr(self.instance, warn_field, None))
            crit_value = attrs.get(crit_field, getattr(self.instance, crit_field, None))
            if warn_value is not None and crit_value is not None and warn_value >= crit_value:
                raise serializers.ValidationError(
                    {warn_field: f"Warning threshold harus lebih kecil dari critical threshold ({crit_field})."}
                )
        return attrs

    def validate_device_offline_threshold_seconds(self, value):
        if value < 10:
            raise serializers.ValidationError("Minimal 10 detik — terlalu kecil akan membuat device sering salah dianggap offline.")
        return value
