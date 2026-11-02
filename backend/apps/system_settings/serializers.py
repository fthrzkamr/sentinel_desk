from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
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
    data_exfil_min_local_files = serializers.IntegerField(min_value=1)
    agent_metrics_interval_seconds = serializers.IntegerField(min_value=5, max_value=300, default=15)

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
            "data_exfil_min_local_files",
            "work_hours_start",
            "work_hours_end",
            "notifications_enabled",
            "telegram_bot_token",
            "telegram_chat_id",
            "webhook_url",
            "notification_emails",
            "agent_metrics_interval_seconds",
            "agent_screen_monitor_enabled",
            "agent_usb_monitor_enabled",
            "agent_app_usage_monitor_enabled",
            "agent_browser_history_monitor_enabled",
            "agent_file_activity_monitor_enabled",
            "agent_idle_activity_monitor_enabled",
            "agent_system_error_monitor_enabled",
            "agent_auto_update_enabled",
            "agent_latest_version",
            "agent_download_url",
            "agent_sha256",
            "stun_server_url",
            "turn_server_enabled",
            "turn_server_url",
            "turn_username",
            "turn_credential",
            "alert_retention_days",
            "audit_retention_days",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_notification_emails(self, value):
        if not value or not value.strip():
            return ""
        cleaned = []
        for raw in value.split(","):
            addr = raw.strip()
            if not addr:
                continue
            try:
                validate_email(addr)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(f"Format email tidak valid: {addr}") from exc
            cleaned.append(addr)
        return ", ".join(cleaned)

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

        bot_token = attrs.get("telegram_bot_token", getattr(self.instance, "telegram_bot_token", "") or "").strip()
        chat_id = attrs.get("telegram_chat_id", getattr(self.instance, "telegram_chat_id", "") or "").strip()
        if bool(bot_token) != bool(chat_id):
            missing_field = "telegram_chat_id" if bot_token else "telegram_bot_token"
            raise serializers.ValidationError(
                {missing_field: "Telegram Bot Token dan Chat ID harus diisi berpasangan (atau kosongkan keduanya)."}
            )
        return attrs

    def validate_device_offline_threshold_seconds(self, value):
        if value < 10:
            raise serializers.ValidationError("Minimal 10 detik — terlalu kecil akan membuat device sering salah dianggap offline.")
        return value
