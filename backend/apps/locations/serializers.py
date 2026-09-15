from rest_framework import serializers

from .models import Location


class LocationIngestSerializer(serializers.Serializer):
    latitude = serializers.FloatField(required=False, allow_null=True, default=None, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, allow_null=True, default=None, min_value=-180, max_value=180)
    accuracy_meters = serializers.FloatField(required=False, allow_null=True, default=None, min_value=0)

    def validate(self, attrs):
        has_lat = attrs.get("latitude") is not None
        has_lng = attrs.get("longitude") is not None
        if has_lat != has_lng:
            raise serializers.ValidationError("latitude and longitude must be provided together.")
        return attrs


class LocationSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    hostname = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = Location
        fields = ["id", "device_id", "hostname", "latitude", "longitude", "accuracy_meters", "source", "recorded_at"]
        read_only_fields = fields
