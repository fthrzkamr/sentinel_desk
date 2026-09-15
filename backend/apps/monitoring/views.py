from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.alerts.services import resolve_connectivity_alert, sync_metric_alerts
from apps.audit.services import get_client_ip
from apps.devices.authentication import DeviceTokenAuthentication, IsDevice
from apps.devices.models import Device

from .broadcast import broadcast_dashboard_event
from .models import DeviceMetric
from .serializers import DeviceMetricSerializer, MetricIngestSerializer
from .services import evaluate_status


class AgentMetricsView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = MetricIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        device: Device = request.auth

        metric = DeviceMetric.objects.create(
            device=device,
            cpu_percent=data.get("cpu_percent"),
            cpu_frequency_mhz=data.get("cpu_frequency_mhz"),
            ram_total_mb=data.get("ram_total_mb"),
            ram_used_mb=data.get("ram_used_mb"),
            ram_percent=data.get("ram_percent"),
            disk_total_gb=data.get("disk_total_gb"),
            disk_used_gb=data.get("disk_used_gb"),
            disk_free_gb=data.get("disk_free_gb"),
            disk_percent=data.get("disk_percent"),
            net_upload_kbps=data.get("net_upload_kbps"),
            net_download_kbps=data.get("net_download_kbps"),
            battery_percent=data.get("battery_percent"),
            battery_charging=data.get("battery_charging"),
            uptime_seconds=data.get("uptime_seconds"),
        )

        previous_status = device.status
        update_fields = ["last_seen", "status", "ip_address"]
        device.ip_address = get_client_ip(request)
        if data.get("username"):
            device.username = data["username"]
            update_fields.append("username")
        if data.get("agent_version"):
            device.agent_version = data["agent_version"]
            update_fields.append("agent_version")

        device.last_seen = timezone.now()
        if device.status != Device.Status.DISABLED:
            device.status = evaluate_status(
                cpu_percent=data.get("cpu_percent"),
                ram_percent=data.get("ram_percent"),
                disk_percent=data.get("disk_percent"),
                battery_percent=data.get("battery_percent"),
                battery_charging=data.get("battery_charging"),
            )
        device.save(update_fields=update_fields)

        broadcast_dashboard_event(
            "device.metric",
            {
                "device_id": device.device_id,
                "status": device.status,
                "last_seen": device.last_seen.isoformat(),
                "cpu_percent": metric.cpu_percent,
                "ram_percent": metric.ram_percent,
                "disk_percent": metric.disk_percent,
                "battery_percent": metric.battery_percent,
                "battery_charging": metric.battery_charging,
            },
        )

        triggered, resolved = sync_metric_alerts(
            device,
            cpu_percent=data.get("cpu_percent"),
            ram_percent=data.get("ram_percent"),
            disk_percent=data.get("disk_percent"),
            battery_percent=data.get("battery_percent"),
            battery_charging=data.get("battery_charging"),
        )
        if previous_status == Device.Status.OFFLINE:
            resolved_connectivity = resolve_connectivity_alert(device)
            if resolved_connectivity:
                resolved.append(resolved_connectivity)
        for alert in triggered:
            broadcast_dashboard_event(
                "alert.triggered",
                {
                    "id": alert.id,
                    "device_id": device.device_id,
                    "category": alert.category,
                    "severity": alert.severity,
                    "message": alert.message,
                },
            )
        for alert in resolved:
            broadcast_dashboard_event(
                "alert.updated",
                {"id": alert.id, "device_id": device.device_id, "status": alert.status},
            )

        return Response({"status": device.status, "server_time": timezone.now()}, status=status.HTTP_201_CREATED)


class DeviceMetricLatestView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("monitoring.view")]

    def get(self, request, device_id):
        device = get_object_or_404(Device, device_id=device_id)
        metric = device.metrics.first()
        if not metric:
            return Response({"detail": "No metrics recorded yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(DeviceMetricSerializer(metric).data)


class DeviceMetricHistoryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("monitoring.view")]
    serializer_class = DeviceMetricSerializer

    def get_queryset(self):
        device = get_object_or_404(Device, device_id=self.kwargs["device_id"])
        return device.metrics.all()
