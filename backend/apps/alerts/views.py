from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.audit.services import log_action
from apps.devices.models import Device
from apps.monitoring.broadcast import broadcast_dashboard_event

from .models import Alert
from .serializers import AlertSerializer
from .services import compute_risk_score


class AlertListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("alert.view")]
    serializer_class = AlertSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "severity", "category"]
    queryset = Alert.objects.select_related(
        "device", "device__assigned_employee", "device__branch", "acknowledged_by", "resolved_by"
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            queryset = queryset.filter(device__device_id=device_id)
        # Unresolved alerts surface on page 1 regardless of age, so an old
        # acknowledged-but-never-resolved alert doesn't hide behind newer
        # resolved ones in the default (unfiltered) view.
        return queryset.annotate(
            is_resolved=Case(
                When(status=Alert.Status.RESOLVED, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).order_by("is_resolved", "-triggered_at")


class AlertSummaryView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("alert.view")]

    def get(self, request):
        open_qs = Alert.objects.filter(status__in=[Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED])
        return Response(
            {
                "open": open_qs.count(),
                "open_critical": open_qs.filter(severity=Alert.Severity.CRITICAL).count(),
                "unacknowledged": Alert.objects.filter(status=Alert.Status.OPEN).count(),
            }
        )


class AlertAcknowledgeView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("alert.manage")]

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk)
        if alert.status != Alert.Status.OPEN:
            return Response(
                {"detail": f"Alert sudah berstatus {alert.status}."}, status=status.HTTP_400_BAD_REQUEST
            )

        alert.status = Alert.Status.ACKNOWLEDGED
        alert.acknowledged_at = timezone.now()
        alert.acknowledged_by = request.user
        alert.save(update_fields=["status", "acknowledged_at", "acknowledged_by"])

        log_action(
            user=request.user,
            action="alert.acknowledged",
            device_id=alert.device.device_id,
            request=request,
            metadata={"alert_id": alert.id, "category": alert.category},
        )
        broadcast_dashboard_event(
            "alert.updated", {"id": alert.id, "device_id": alert.device.device_id, "status": alert.status}
        )
        return Response(AlertSerializer(alert).data)


class AlertResolveView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("alert.manage")]

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk)
        if alert.status == Alert.Status.RESOLVED:
            return Response({"detail": "Alert sudah resolved."}, status=status.HTTP_400_BAD_REQUEST)

        alert.status = Alert.Status.RESOLVED
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.save(update_fields=["status", "resolved_at", "resolved_by"])

        log_action(
            user=request.user,
            action="alert.resolved",
            device_id=alert.device.device_id,
            request=request,
            metadata={"alert_id": alert.id, "category": alert.category},
        )
        broadcast_dashboard_event(
            "alert.updated", {"id": alert.id, "device_id": alert.device.device_id, "status": alert.status}
        )
        return Response(AlertSerializer(alert).data)


class DeviceRiskScoreView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("alert.view")]

    def get(self, request, device_id):
        device = get_object_or_404(Device, device_id=device_id)
        return Response(compute_risk_score(device))
