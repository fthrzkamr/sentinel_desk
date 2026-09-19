from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.audit.services import get_client_ip, log_action

from .authentication import DeviceTokenAuthentication, IsDevice
from .models import AgentRelease, Branch, Company, Department, Device, DeviceCredential, Employee, EnrollmentToken
from .serializers import (
    AgentReleaseSerializer,
    BranchSerializer,
    CompanySerializer,
    DepartmentSerializer,
    DeviceOrgAssignmentSerializer,
    DeviceSerializer,
    EmployeeSerializer,
    EnrollmentTokenCreateSerializer,
    EnrollmentTokenSerializer,
    EnrollRequestSerializer,
    HeartbeatSerializer,
)


class EnrollmentTokenListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("agent.manage")]
    queryset = EnrollmentToken.objects.select_related("created_by", "used_by_device").all()
    serializer_class = EnrollmentTokenSerializer

    def create(self, request, *args, **kwargs):
        input_serializer = EnrollmentTokenCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        ttl_minutes = input_serializer.validated_data.get(
            "ttl_minutes", settings.ENROLLMENT_TOKEN_TTL_MINUTES
        )
        token, raw_token = EnrollmentToken.create_with_token(
            created_by=request.user,
            ttl_minutes=ttl_minutes,
            label=input_serializer.validated_data.get("label", ""),
            company=input_serializer.validated_data.get("company"),
            branch=input_serializer.validated_data.get("branch"),
            department=input_serializer.validated_data.get("department"),
            assigned_employee=input_serializer.validated_data.get("assigned_employee"),
        )

        log_action(
            user=request.user,
            action="agent.enrollment_token_created",
            request=request,
            metadata={"token_id": token.id, "label": token.label},
        )

        return Response(
            {
                "id": token.id,
                "token": raw_token,
                "expires_at": token.expires_at,
                "label": token.label,
            },
            status=status.HTTP_201_CREATED,
        )


class EnrollmentTokenRevokeView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("agent.manage")]

    def post(self, request, pk):
        try:
            token = EnrollmentToken.objects.get(pk=pk)
        except EnrollmentToken.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        token.revoked = True
        token.save(update_fields=["revoked"])
        log_action(
            user=request.user,
            action="agent.enrollment_token_revoked",
            request=request,
            metadata={"token_id": token.id},
        )
        return Response(EnrollmentTokenSerializer(token).data)


class AgentEnrollView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = EnrollRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        raw_token = data.pop("token")

        candidates = EnrollmentToken.objects.filter(
            revoked=False, used_at__isnull=True, expires_at__gt=timezone.now()
        )
        matched_token = next((t for t in candidates if t.check_token(raw_token)), None)

        if matched_token is None:
            log_action(
                action="agent.enroll_failed",
                request=request,
                metadata={"hostname": data.get("hostname", "")},
            )
            return Response(
                {"detail": "Invalid, expired, or already-used enrollment token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        device = Device.objects.create(
            ip_address=get_client_ip(request),
            company=matched_token.company,
            branch=matched_token.branch,
            department=matched_token.department,
            assigned_employee=matched_token.assigned_employee,
            **data,
        )
        matched_token.mark_used(device)
        credential, raw_device_token = DeviceCredential.create_for_device(device)

        log_action(
            user=matched_token.created_by,
            action="device.registered",
            device_id=device.device_id,
            request=request,
            metadata={"enrollment_token_id": matched_token.id, "hostname": device.hostname},
        )

        return Response(
            {"device_id": device.device_id, "device_token": raw_device_token},
            status=status.HTTP_201_CREATED,
        )


class AgentHeartbeatView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: Device = request.auth

        update_fields = ["last_seen", "status", "ip_address"]
        device.ip_address = get_client_ip(request)
        if serializer.validated_data.get("username"):
            device.username = serializer.validated_data["username"]
            update_fields.append("username")
        if serializer.validated_data.get("agent_version"):
            device.agent_version = serializer.validated_data["agent_version"]
            update_fields.append("agent_version")

        device.last_seen = timezone.now()
        if device.status != Device.Status.DISABLED:
            device.status = Device.Status.ONLINE
        device.save(update_fields=update_fields)

        return Response({"status": device.status, "server_time": timezone.now()})


class DeviceListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.view")]
    serializer_class = DeviceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "company", "branch", "department"]
    search_fields = ["device_id", "hostname", "username"]
    queryset = Device.objects.select_related(
        "company", "branch", "department", "assigned_employee"
    ).all()


class DeviceDetailView(generics.RetrieveUpdateAPIView):
    # Viewing needs only device.view (most roles have it); changing the
    # org assignment is a device.manage action — narrower, matching the
    # enrollment-token-time assignment path in AgentEnrollView above.
    http_method_names = ["get", "patch", "head", "options"]
    lookup_field = "device_id"
    lookup_url_kwarg = "device_id"
    queryset = Device.objects.select_related(
        "company", "branch", "department", "assigned_employee"
    ).all()

    def get_permissions(self):
        code = "device.manage" if self.request.method == "PATCH" else "device.view"
        return [IsAuthenticated(), HasPermission(code)()]

    def get_serializer_class(self):
        return DeviceOrgAssignmentSerializer if self.request.method == "PATCH" else DeviceSerializer

    def update(self, request, *args, **kwargs):
        device = self.get_object()
        serializer = DeviceOrgAssignmentSerializer(device, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(
            user=request.user,
            action="device.updated",
            device_id=device.device_id,
            request=request,
            metadata={"changed_fields": list(request.data.keys())},
        )
        return Response(DeviceSerializer(device).data)


class DeviceDisableView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("device.disable")]

    def post(self, request, device_id):
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        device.status = Device.Status.DISABLED
        device.save(update_fields=["status"])
        log_action(
            user=request.user, action="device.disabled", device_id=device.device_id, request=request
        )
        return Response(DeviceSerializer(device).data)


class DeviceEnableView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("device.disable")]

    def post(self, request, device_id):
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        device.status = Device.Status.OFFLINE
        device.save(update_fields=["status"])
        log_action(
            user=request.user, action="device.enabled", device_id=device.device_id, request=request
        )
        return Response(DeviceSerializer(device).data)


# --- Org structure (Company/Branch/Department/Employee) ---
# Reference data an admin sets up once, then picks from when creating an
# enrollment token (see EnrollmentTokenListCreateView.create above) so a
# device is assigned the moment it enrolls rather than needing a separate
# edit afterward.


class CompanyListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    queryset = Company.objects.all()
    serializer_class = CompanySerializer


class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    queryset = Company.objects.all()
    serializer_class = CompanySerializer


class BranchListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    serializer_class = BranchSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["company"]
    queryset = Branch.objects.select_related("company").all()


class BranchDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer


class DepartmentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    serializer_class = DepartmentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["branch"]
    queryset = Department.objects.select_related("branch", "branch__company").all()


class DepartmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer


class EmployeeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    serializer_class = EmployeeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["department"]
    queryset = Employee.objects.select_related("department").all()


class EmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.manage")]
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer


# --- Agent self-update ---
# An admin uploads a new .exe build once (AgentReleaseListCreateView) and
# marks it active; every agent's own periodic check (AgentVersionView) then
# picks it up and — if newer than its own AGENT_VERSION — downloads it
# (AgentDownloadView), verifies the sha256 computed at upload time, and
# swaps its own executable. No manual re-deployment to each laptop needed.


class AgentVersionView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def get(self, request):
        release = AgentRelease.get_active()
        if not release:
            return Response({"detail": "No active release configured."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "version": release.version,
                "sha256": release.sha256,
                "file_size": release.file_size,
                "notes": release.notes,
            }
        )


class AgentDownloadView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def get(self, request):
        release = AgentRelease.get_active()
        if not release or not release.exe_file:
            return Response({"detail": "No active release configured."}, status=status.HTTP_404_NOT_FOUND)

        device: Device = request.auth
        log_action(
            action="agent.update_downloaded",
            device_id=device.device_id,
            request=request,
            metadata={"version": release.version},
        )
        response = FileResponse(release.exe_file.open("rb"), content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="SentinelDeskAgent-{release.version}.exe"'
        response["Content-Length"] = release.file_size
        return response


class AgentReleaseListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("agent.manage")]
    serializer_class = AgentReleaseSerializer
    queryset = AgentRelease.objects.select_related("uploaded_by").all()

    def perform_create(self, serializer):
        release = serializer.save(uploaded_by=self.request.user)
        log_action(
            user=self.request.user,
            action="agent.release_uploaded",
            request=self.request,
            metadata={"version": release.version, "is_active": release.is_active},
        )


class AgentReleaseDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasPermission("agent.manage")]
    queryset = AgentRelease.objects.all()
    serializer_class = AgentReleaseSerializer

    def perform_update(self, serializer):
        release = serializer.save()
        log_action(
            user=self.request.user,
            action="agent.release_updated",
            request=self.request,
            metadata={"version": release.version, "is_active": release.is_active},
        )
