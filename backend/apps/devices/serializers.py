from rest_framework import serializers

from .models import Device, EnrollmentToken


class DeviceSerializer(serializers.ModelSerializer):
    company = serializers.StringRelatedField()
    branch = serializers.StringRelatedField()
    department = serializers.StringRelatedField()
    assigned_employee = serializers.StringRelatedField()

    class Meta:
        model = Device
        fields = [
            "id",
            "device_id",
            "hostname",
            "computer_name",
            "username",
            "os_name",
            "os_version",
            "architecture",
            "cpu",
            "ram",
            "disk",
            "serial_number",
            "manufacturer",
            "model",
            "mac_address",
            "ip_address",
            "agent_version",
            "status",
            "last_seen",
            "first_registered",
            "company",
            "branch",
            "department",
            "assigned_employee",
        ]
        read_only_fields = fields


class EnrollmentTokenSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField()
    used_by_device = serializers.SlugRelatedField(slug_field="device_id", read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = EnrollmentToken
        fields = [
            "id",
            "token_prefix",
            "label",
            "created_by",
            "created_at",
            "expires_at",
            "used_at",
            "used_by_device",
            "revoked",
            "is_valid",
        ]
        read_only_fields = fields


class EnrollmentTokenCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    ttl_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080)


class EnrollRequestSerializer(serializers.Serializer):
    token = serializers.CharField()
    hostname = serializers.CharField(max_length=150)
    computer_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    os_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    os_version = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    architecture = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    cpu = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    ram = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    disk = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    serial_number = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    manufacturer = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    model = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    mac_address = serializers.CharField(max_length=17, required=False, allow_blank=True, default="")
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class HeartbeatSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True)
