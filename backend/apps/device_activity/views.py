from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.alerts.services import resolve_usb_alert, trigger_usb_alert
from apps.devices.authentication import DeviceTokenAuthentication, IsDevice
from apps.devices.models import Device

from .models import AppUsage, BrowsingHistoryEntry, FileActivityEvent
from .serializers import (
    AppUsageIngestSerializer,
    AppUsageSerializer,
    BrowsingHistoryIngestSerializer,
    BrowsingHistorySerializer,
    FileActivityIngestSerializer,
    FileActivitySerializer,
    UsbEventSerializer,
)


class AgentAppUsageSyncView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = AppUsageIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: Device = request.auth

        for item in serializer.validated_data["items"]:
            usage, created = AppUsage.objects.get_or_create(
                device=device,
                app_name=item["app_name"],
                date=item["date"],
                defaults={"window_title": item["window_title"], "duration_seconds": item["duration_seconds"]},
            )
            if not created:
                usage.window_title = item["window_title"] or usage.window_title
                usage.duration_seconds = F("duration_seconds") + item["duration_seconds"]
                usage.save(update_fields=["window_title", "duration_seconds", "last_seen"])

        return Response(status=status.HTTP_201_CREATED)


class AgentBrowsingHistorySyncView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = BrowsingHistoryIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: Device = request.auth

        entries = [
            BrowsingHistoryEntry(
                device=device,
                browser=item["browser"],
                url=item["url"],
                title=item["title"],
                visited_at=item["visited_at"],
            )
            for item in serializer.validated_data["items"]
        ]
        BrowsingHistoryEntry.objects.bulk_create(entries, ignore_conflicts=True)
        return Response(status=status.HTTP_201_CREATED)


class AgentFileActivitySyncView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = FileActivityIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: Device = request.auth

        events = [
            FileActivityEvent(
                device=device,
                event_type=item["event_type"],
                path=item["path"],
                destination_path=item["destination_path"],
                occurred_at=item["occurred_at"],
            )
            for item in serializer.validated_data["items"]
        ]
        FileActivityEvent.objects.bulk_create(events)
        return Response(status=status.HTTP_201_CREATED)


class AgentUsbEventView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = UsbEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        device: Device = request.auth

        if data["event"] == "connected":
            trigger_usb_alert(device, label=data["label"], drive_letter=data["drive_letter"], serial=data["serial"])
        else:
            resolve_usb_alert(device)

        return Response(status=status.HTTP_201_CREATED)


class AppUsageListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = AppUsageSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {"device__device_id": ["exact"], "date": ["exact", "gte", "lte"]}
    ordering_fields = ["date", "duration_seconds", "app_name"]
    ordering = ["-date", "-duration_seconds"]
    queryset = AppUsage.objects.select_related("device").all()


class BrowsingHistoryListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = BrowsingHistorySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {"device__device_id": ["exact"]}
    search_fields = ["url", "title"]
    queryset = BrowsingHistoryEntry.objects.select_related("device").all()


class FileActivityListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = FileActivitySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {"device__device_id": ["exact"], "event_type": ["exact"]}
    search_fields = ["path"]
    queryset = FileActivityEvent.objects.select_related("device").all()
