from django.db import transaction
from django_filters import rest_framework as django_filters
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.devices.authentication import DeviceTokenAuthentication, IsDevice
from apps.devices.models import Device

from .models import Software
from .serializers import SoftwareSerializer, SoftwareSyncSerializer


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
