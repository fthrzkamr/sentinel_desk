from django.conf import settings
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
from .models import Branch, Company, Department, Device, DeviceCredential, Employee, EnrollmentToken
from .serializers import (
    BranchSerializer,
    CompanySerializer,
    DepartmentSerializer,
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


class DeviceDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.view")]
    serializer_class = DeviceSerializer
    lookup_field = "device_id"
    lookup_url_kwarg = "device_id"
    queryset = Device.objects.select_related(
        "company", "branch", "department", "assigned_employee"
    ).all()


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
