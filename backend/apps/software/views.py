from django.db import transaction
from django_filters import rest_framework as django_filters
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.alerts.services import trigger_new_software_alert
from apps.devices.authentication import DeviceTokenAuthentication, IsDevice
from apps.devices.models import Device
from apps.monitoring.broadcast import broadcast_alert_triggered

from .models import Software, SoftwareWhitelistEntry
from .serializers import SoftwareSerializer, SoftwareSyncSerializer, SoftwareWhitelistEntrySerializer


class AgentSoftwareSyncView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = SoftwareSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: Device = request.auth
        items = serializer.validated_data["items"]

        existing_names = set(Software.objects.filter(device=device).values_list("name", flat=True))
        incoming_names = {item["name"] for item in items}
        # Only the device's very first-ever sync has no prior baseline to
        # diff against — skip alerting then so initial enrollment doesn't
        # fire one alert per already-installed app.
        new_names = sorted(incoming_names - existing_names) if existing_names else []

        with transaction.atomic():
            Software.objects.filter(device=device).delete()
            Software.objects.bulk_create(
                [
                    Software(
                        device=device,
                        name=item["name"],
                        version=item["version"],
                        publisher=item["publisher"],
                        install_date=item["install_date"],
                    )
                    for item in items
                ],
                ignore_conflicts=True,
            )

        if new_names:
            whitelist = set(SoftwareWhitelistEntry.objects.values_list("name", flat=True))
            if whitelist:
                unauthorized_names = sorted(name for name in new_names if name not in whitelist)
                if unauthorized_names:
                    broadcast_alert_triggered(
                        trigger_new_software_alert(device, names=unauthorized_names, unauthorized=True)
                    )
            else:
                broadcast_alert_triggered(trigger_new_software_alert(device, names=new_names))

        return Response({"synced": len(items)}, status=status.HTTP_201_CREATED)


class SoftwareFilter(django_filters.FilterSet):
    device = django_filters.CharFilter(field_name="device__device_id")

    class Meta:
        model = Software
        fields = ["device"]


class SoftwareListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("software.view")]
    serializer_class = SoftwareSerializer
    queryset = Software.objects.select_related("device").all()
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = SoftwareFilter
    search_fields = ["name", "publisher"]
    ordering_fields = ["name", "version", "publisher", "install_date", "collected_at"]
    ordering = ["name"]


class SoftwareWhitelistListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("software.manage")]
    serializer_class = SoftwareWhitelistEntrySerializer
    queryset = SoftwareWhitelistEntry.objects.all()
    pagination_class = None

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)


class SoftwareWhitelistDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, HasPermission("software.manage")]
    queryset = SoftwareWhitelistEntry.objects.all()
