from rest_framework import serializers

from .models import Software


class SoftwareIngestItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    version = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    publisher = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    install_date = serializers.DateField(required=False, allow_null=True, default=None)


class SoftwareSyncSerializer(serializers.Serializer):
    items = SoftwareIngestItemSerializer(many=True)


class SoftwareSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = Software
        fields = ["id", "device_id", "hostname", "name", "version", "publisher", "install_date", "collected_at"]
        read_only_fields = fields
