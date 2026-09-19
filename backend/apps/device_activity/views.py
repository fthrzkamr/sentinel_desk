import re

from django.db.models import F
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.alerts.services import (
    check_out_of_hours_activity,
    resolve_usb_alert,
    trigger_data_exfil_alert,
    trigger_usb_alert,
)
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
        items = serializer.validated_data["items"]

        for item in items:
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

        # AppUsage only carries a date, not a precise timestamp — "now" (this
        # sync just happened, on a 5-minute interval) is a close enough proxy
        # for when the usage occurred to bucket it into an hour-of-day check.
        if items:
            check_out_of_hours_activity(device, timezone.now(), f"App usage: {items[0]['app_name']}")

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

        items = serializer.validated_data["items"]
        entries = [
            BrowsingHistoryEntry(
                device=device,
                browser=item["browser"],
                url=item["url"],
                title=item["title"],
                visited_at=item["visited_at"],
            )
            for item in items
        ]
        BrowsingHistoryEntry.objects.bulk_create(entries, ignore_conflicts=True)

        for item in items:
            check_out_of_hours_activity(device, item["visited_at"], f"Browsing: {item['url'][:80]}")

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
        items = serializer.validated_data["items"]

        events = [
            FileActivityEvent(
                device=device,
                event_type=item["event_type"],
                path=item["path"],
                destination_path=item["destination_path"],
                source=item["source"],
                occurred_at=item["occurred_at"],
            )
            for item in items
        ]
        FileActivityEvent.objects.bulk_create(events)

        for item in items:
            check_out_of_hours_activity(
                device, item["occurred_at"], f"File {item['event_type'].lower()}: {item['path'][:80]}"
            )
            if item["source"] == FileActivityEvent.Source.USB and item["event_type"] in (
                FileActivityEvent.EventType.CREATED,
                FileActivityEvent.EventType.MODIFIED,
            ):
                # Real agent paths are always "F:\..." (backslash), but be
                # tolerant of "F:/..." too rather than accidentally treating
                # the whole path as the drive label when there's no backslash.
                drive_match = re.match(r"^[A-Za-z]:", item["path"])
                drive_letter = drive_match.group(0) if drive_match else item["path"][:3]
                trigger_data_exfil_alert(
                    device, drive_letter=drive_letter, event_type=item["event_type"], path=item["path"]
                )

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
