from rest_framework import serializers

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)
    assigned_employee = serializers.StringRelatedField(source="device.assigned_employee")
    branch = serializers.StringRelatedField(source="device.branch")
    acknowledged_by_username = serializers.CharField(source="acknowledged_by.username", read_only=True)
    resolved_by_username = serializers.CharField(source="resolved_by.username", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "device_id",
            "hostname",
            "assigned_employee",
            "branch",
            "category",
            "severity",
            "status",
            "message",
            "metadata",
            "triggered_at",
            "acknowledged_at",
            "acknowledged_by_username",
            "resolved_at",
            "resolved_by_username",
        ]
        read_only_fields = fields
