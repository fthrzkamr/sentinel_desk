import datetime
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
    FILE_SHARING_DOMAINS,
    check_out_of_hours_activity,
    resolve_usb_alert,
    trigger_cloud_upload_alert,
    trigger_data_exfil_alert,
    trigger_suspicious_url_alert,
    trigger_system_error_alert,
    trigger_usb_alert,
)
from apps.alerts.url_analysis import classify_url
from apps.devices.authentication import DeviceTokenAuthentication, IsDevice
from apps.devices.models import Device

from .models import AppUsage, BrowsingHistoryEntry, FileActivityEvent, IdleActivityStat, SystemErrorEvent
from .serializers import (
    AppUsageIngestSerializer,
    AppUsageSerializer,
    BrowsingHistoryIngestSerializer,
    BrowsingHistorySerializer,
    FileActivityIngestSerializer,
    FileActivitySerializer,
    IdleActivityIngestSerializer,
    IdleActivityStatSerializer,
    SystemErrorIngestSerializer,
    SystemErrorSerializer,
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


class AgentIdleActivitySyncView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = IdleActivityIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: Device = request.auth
        items = serializer.validated_data["items"]

        for item in items:
            stat, created = IdleActivityStat.objects.get_or_create(
                device=device,
                date=item["date"],
                defaults={"active_seconds": item["active_seconds"], "idle_seconds": item["idle_seconds"]},
            )
            if not created:
                stat.active_seconds = F("active_seconds") + item["active_seconds"]
                stat.idle_seconds = F("idle_seconds") + item["idle_seconds"]
                stat.save(update_fields=["active_seconds", "idle_seconds", "last_seen"])

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
            reasons = classify_url(item["url"])
            if reasons:
                trigger_suspicious_url_alert(device, url=item["url"], title=item["title"], reasons=reasons)
            if any(domain in item["url"] for domain in FILE_SHARING_DOMAINS):
                ten_min_ago = item["visited_at"] - datetime.timedelta(minutes=10)
                recent_count = FileActivityEvent.objects.filter(
                    device=device,
                    source=FileActivityEvent.Source.LOCAL,
                    event_type__in=[FileActivityEvent.EventType.CREATED, FileActivityEvent.EventType.MODIFIED],
                    occurred_at__gte=ten_min_ago,
                    occurred_at__lte=item["visited_at"],
                ).count()
                trigger_cloud_upload_alert(device, url=item["url"], recent_local_file_count=recent_count)

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


class AgentSystemErrorSyncView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = SystemErrorIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: Device = request.auth
        items = serializer.validated_data["items"]

        events = [
            SystemErrorEvent(
                device=device,
                log_name=item["log_name"],
                provider=item["provider"],
                event_id=item["event_id"],
                level=item["level"],
                message=item["message"],
                occurred_at=item["occurred_at"],
            )
            for item in items
        ]
        SystemErrorEvent.objects.bulk_create(events, ignore_conflicts=True)

        for item in items:
            if item["level"] == SystemErrorEvent.Level.CRITICAL:
                trigger_system_error_alert(
                    device, provider=item["provider"], event_id=item["event_id"], message=item["message"]
                )

        return Response(status=status.HTTP_201_CREATED)


class AppUsageListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = AppUsageSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {"device__device_id": ["exact"], "date": ["exact", "gte", "lte"]}
    ordering_fields = ["date", "duration_seconds", "app_name"]
    ordering = ["-date", "-duration_seconds"]
    queryset = AppUsage.objects.select_related("device").all()


class IdleActivityListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = IdleActivityStatSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {"device__device_id": ["exact"], "date": ["exact", "gte", "lte"]}
    queryset = IdleActivityStat.objects.select_related("device").all()


class BrowsingHistoryListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = BrowsingHistorySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {"device__device_id": ["exact"], "visited_at": ["gte", "lte"]}
    search_fields = ["url", "title"]
    queryset = BrowsingHistoryEntry.objects.select_related("device").all()


class FileActivityListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = FileActivitySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {
        "device__device_id": ["exact"],
        "event_type": ["exact"],
        "occurred_at": ["gte", "lte"],
    }
    search_fields = ["path"]
    queryset = FileActivityEvent.objects.select_related("device").all()


class SystemErrorListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("activity.view")]
    serializer_class = SystemErrorSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {
        "device__device_id": ["exact"],
        "level": ["exact"],
        "occurred_at": ["gte", "lte"],
    }
    search_fields = ["provider", "message"]
    queryset = SystemErrorEvent.objects.select_related("device").all()


