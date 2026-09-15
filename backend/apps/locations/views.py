from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.audit.services import get_client_ip
from apps.devices.authentication import DeviceTokenAuthentication, IsDevice
from apps.devices.models import Device

from .models import Location
from .serializers import LocationIngestSerializer, LocationSerializer
from .services import estimate_location_from_ip


class AgentLocationView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = LocationIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        device: Device = request.auth

        if data["latitude"] is not None:
            location = Location.objects.create(
                device=device,
                latitude=data["latitude"],
                longitude=data["longitude"],
                accuracy_meters=data["accuracy_meters"],
                source=Location.Source.OS,
            )
        else:
            estimate = estimate_location_from_ip(get_client_ip(request))
            location = Location.objects.create(device=device, source=Location.Source.IP, **estimate)

        return Response(LocationSerializer(location).data, status=status.HTTP_201_CREATED)


class LocationLatestListView(generics.ListAPIView):
    """Latest known location per device — for the map overview."""

    permission_classes = [IsAuthenticated, HasPermission("location.view")]
    serializer_class = LocationSerializer

    def get_queryset(self):
        return (
            Location.objects.select_related("device")
            .order_by("device_id", "-recorded_at")
            .distinct("device_id")
        )


class DeviceLocationHistoryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("location.view")]
    serializer_class = LocationSerializer

    def get_queryset(self):
        device = get_object_or_404(Device, device_id=self.kwargs["device_id"])
        return device.locations.all()
