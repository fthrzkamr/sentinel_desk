from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasPermission

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("audit.view")]
    serializer_class = AuditLogSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["action", "device_id"]
    search_fields = ["action", "device_id", "user__username"]
    queryset = AuditLog.objects.select_related("user").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        username = self.request.query_params.get("username")
        if username:
            queryset = queryset.filter(user__username=username)
        created_after = self.request.query_params.get("created_after")
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        created_before = self.request.query_params.get("created_before")
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        return queryset
