from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db.models import Count, F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.alerts.services import RISK_CATEGORY_WEIGHTS, RISK_WINDOW_DAYS, compute_risk_score
from apps.audit.services import get_client_ip, log_action

from .asset_matching import find_asset_candidates_by_spec, find_employee_by_name, rematch_unlinked_assets, sync_asset
from .authentication import DeviceTokenAuthentication, IsDevice
from .models import (
    Asset,
    Branch,
    Company,
    Department,
    Device,
    DeviceCredential,
    Employee,
    EnrollmentToken,
)
from .policy import get_agent_remote_payload
from .serializers import (
    AssetLinkSerializer,
    AssetSerializer,
    AssetSetUserSerializer,
    AssetSyncSerializer,
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
            is_reusable=input_serializer.validated_data.get("is_reusable", False),
        )

        log_action(
            user=request.user,
            action="agent.enrollment_token_created",
            request=request,
            metadata={"token_id": token.id, "label": token.label, "is_reusable": token.is_reusable},
        )

        return Response(
            {
                "id": token.id,
                "token": raw_token,
                "expires_at": token.expires_at,
                "label": token.label,
                "is_reusable": token.is_reusable,
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
        raw_token = (data.pop("token", "") or "").strip()
        matched_token = None

        if raw_token:
            candidates = EnrollmentToken.objects.filter(
                Q(used_at__isnull=True) | Q(is_reusable=True),
                revoked=False,
                expires_at__gt=timezone.now(),
            )
            matched_token = next((t for t in candidates if t.check_token(raw_token)), None)

            if matched_token is None:
                log_action(
                    action="agent.enroll_failed",
                    request=request,
                    metadata={"hostname": data.get("hostname", ""), "reason": "invalid_token"},
                )
                return Response(
                    {"detail": "Invalid, expired, or already-used enrollment token."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        mac_address = data.get("mac_address") or ""
        existing_device = (
            Device.objects.exclude(mac_address="").filter(mac_address=mac_address).first() if mac_address else None
        )

        if existing_device:
            # Same physical laptop enrolling again (agent reinstalled after a
            # wipe/reimage, etc.) — reuse its device_id and history instead of
            # spawning a duplicate "ghost" device that never reports in again.
            device = existing_device
            reenroll_metadata = {
                "mac_address": mac_address,
                "previous_hostname": device.hostname,
                "previous_assigned_employee": str(device.assigned_employee) if device.assigned_employee else None,
                "new_hostname": data.get("hostname", ""),
                "new_assigned_employee": str(matched_token.assigned_employee) if (matched_token and matched_token.assigned_employee) else None,
            }
            for field, value in data.items():
                setattr(device, field, value)
            device.ip_address = get_client_ip(request)
            if matched_token:
                if matched_token.company_id:
                    device.company = matched_token.company
                if matched_token.branch_id:
                    device.branch = matched_token.branch
                if matched_token.department_id:
                    device.department = matched_token.department
                if matched_token.assigned_employee_id:
                    device.assigned_employee = matched_token.assigned_employee

            device.status = Device.Status.OFFLINE
            device.last_seen = None
            device.save()
            DeviceCredential.objects.filter(device=device).delete()
            action = "device.reenrolled"
            metadata = {"enrollment_token_id": matched_token.id if matched_token else None, **reenroll_metadata}
        else:
            # Auto-enrolled without token starts unapproved (Pending Approval)
            is_approved = bool(matched_token and not matched_token.is_reusable)
            device = Device.objects.create(
                ip_address=get_client_ip(request),
                company=matched_token.company if matched_token else None,
                branch=matched_token.branch if matched_token else None,
                department=matched_token.department if matched_token else None,
                assigned_employee=matched_token.assigned_employee if matched_token else None,
                is_approved=is_approved,
                **data,
            )
            action = "device.registered"
            metadata = {
                "enrollment_token_id": matched_token.id if matched_token else None,
                "hostname": device.hostname,
                "auto_enrolled": matched_token is None,
            }

        if matched_token:
            matched_token.mark_used(device)

        credential, raw_device_token = DeviceCredential.create_for_device(device)
        rematch_unlinked_assets(device)

        log_action(
            user=matched_token.created_by if matched_token else None,
            action=action,
            device_id=device.device_id,
            request=request,
            metadata=metadata,
        )

        return Response(
            {
                "device_id": device.device_id,
                "device_token": raw_device_token,
                "is_approved": device.is_approved,
            },
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

        return Response(get_agent_remote_payload(device_status=device.status))


class AgentDownloadView(APIView):
    """Serves the latest or specified agent release .exe to authenticated devices
    or administrators. Kept out of standard public MEDIA_URL."""

    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]

    def get(self, request, version=None):
        import os
        from apps.system_settings.models import SystemSettings

        if not version or version == "latest":
            version = SystemSettings.get_solo().agent_latest_version

        if not version:
            raise Http404("No agent release version specified or configured.")

        filename = f"SentinelDeskAgent-{version}.exe"
        file_path = settings.MEDIA_ROOT / "agent" / filename
        if not os.path.exists(file_path):
            raise Http404(f"Release binary {filename} not found.")

        return FileResponse(open(file_path, "rb"), as_attachment=True, filename=filename)


class DeviceListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.view")]
    serializer_class = DeviceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "company", "branch", "department"]
    search_fields = ["device_id", "hostname", "username", "assets__asset_code"]
    queryset = Device.objects.select_related(
        "company", "branch", "department", "assigned_employee"
    ).prefetch_related("assets").all()


class DashboardSummaryView(APIView):
    """Fleet-wide aggregated counts, security compliance posture, and top
    insider-threat risk devices for the main Dashboard page. Computed at the
    DB level so counts stay exact even when the fleet exceeds a single
    paginated DeviceListView response."""

    permission_classes = [IsAuthenticated, HasPermission("device.view")]

    def get(self, request):
        status_rows = Device.objects.values("status").annotate(count=Count("id"))
        status_counts = {
            "total": 0,
            Device.Status.ONLINE: 0,
            Device.Status.OFFLINE: 0,
            Device.Status.WARNING: 0,
            Device.Status.CRITICAL: 0,
            Device.Status.DISABLED: 0,
            "pending_approval": Device.objects.filter(is_approved=False).count(),
        }
        for row in status_rows:
            s = row["status"]
            c = row["count"]
            status_counts["total"] += c
            if s in status_counts:
                status_counts[s] = c

        active_qs = Device.objects.exclude(status=Device.Status.DISABLED)
        compliance = {
            "active_total": active_qs.count(),
            "bitlocker_off": active_qs.filter(bitlocker_enabled=False).count(),
            "firewall_off": active_qs.filter(firewall_enabled=False).count(),
            "antivirus_off": active_qs.filter(antivirus_enabled=False).count(),
            "low_battery_health": active_qs.filter(
                battery_design_capacity_mwh__gt=0,
                battery_full_charge_capacity_mwh__isnull=False,
                battery_full_charge_capacity_mwh__lt=F("battery_design_capacity_mwh") * 0.5,
            ).count(),
            "fully_compliant": active_qs.filter(
                bitlocker_enabled=True,
                firewall_enabled=True,
                antivirus_enabled=True,
            ).count(),
        }

        since = timezone.now() - timezone.timedelta(days=RISK_WINDOW_DAYS)
        risk_candidates = (
            Device.objects.filter(
                alerts__category__in=list(RISK_CATEGORY_WEIGHTS.keys()),
                alerts__triggered_at__gte=since,
            )
            .distinct()
            .select_related("assigned_employee", "branch")
            .prefetch_related("alerts")
        )
        scored_devices = []
        for dev in risk_candidates:
            risk = compute_risk_score(dev, window_days=RISK_WINDOW_DAYS)
            if risk["score"] > 0:
                scored_devices.append(
                    {
                        "device_id": dev.device_id,
                        "hostname": dev.hostname,
                        "assigned_employee": str(dev.assigned_employee) if dev.assigned_employee else None,
                        "branch": dev.branch.name if dev.branch else None,
                        "status": dev.status,
                        "score": risk["score"],
                        "level": risk["level"],
                        "breakdown": risk["breakdown"],
                    }
                )
        scored_devices.sort(key=lambda item: item["score"], reverse=True)

        return Response(
            {
                "status_counts": status_counts,
                "compliance": compliance,
                "high_risk_devices": scored_devices[:5],
            }
        )


class DeviceDetailView(generics.RetrieveUpdateAPIView):
    # Viewing needs only device.view (most roles have it); changing the
    # org assignment is a device.manage action — narrower, matching the
    # enrollment-token-time assignment path in AgentEnrollView above.
    http_method_names = ["get", "patch", "head", "options"]
    lookup_field = "device_id"
    lookup_url_kwarg = "device_id"
    queryset = Device.objects.select_related(
        "company", "branch", "department", "assigned_employee"
    ).prefetch_related("assets").all()

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

        # If employee was assigned, automatically cascade company, branch, and department
        # so they follow the employee data as expected by the admin
        if device.assigned_employee and device.assigned_employee.department:
            emp_dept = device.assigned_employee.department
            need_save = False
            if not request.data.get("department"):
                device.department = emp_dept
                need_save = True
            if emp_dept.branch:
                if not request.data.get("branch"):
                    device.branch = emp_dept.branch
                    need_save = True
                if emp_dept.branch.company:
                    if not request.data.get("company"):
                        device.company = emp_dept.branch.company
                        need_save = True
            if need_save:
                device.save(update_fields=["department", "branch", "company"])

        rematch_unlinked_assets(device)
        # Mirror of AssetSetUserView's own cascade (see its comment) - an
        # admin reassigning this device straight from Device Detail should
        # just as reliably update any asset already linked to it, not only
        # the direction that started on the Assets page. user_status kept
        # in step too, for the same reason AssetSetUserView does it.
        device.assets.update(
            current_employee=device.assigned_employee,
            user_status=Asset.UserStatus.IDENTIFIED if device.assigned_employee else Asset.UserStatus.INCOMPLETE,
        )
        log_action(
            user=request.user,
            action="device.updated",
            device_id=device.device_id,
            request=request,
            metadata={"changed_fields": list(request.data.keys())},
        )
        return Response(DeviceSerializer(device).data)


class DeviceAssetSuggestionsView(APIView):
    """Candidate Assets for a Device that has no assigned_employee yet -
    see find_asset_candidates_by_spec's own docstring for why this exists
    (hardware-spec comparison, not name-based, specifically for a blank
    device with nothing to compare a name against). Read-only: picking one
    still goes through AssetLinkView, same as any other manual link."""

    permission_classes = [IsAuthenticated, HasPermission("device.view")]

    def get(self, request, device_id):
        device = get_object_or_404(Device, device_id=device_id)
        scored = find_asset_candidates_by_spec(device)
        results = []
        for asset, score in scored:
            data = AssetSerializer(asset).data
            data["spec_score"] = round(score, 3)
            results.append(data)
        return Response(results)


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


class DeviceApproveView(APIView):
    """Confirms a device that enrolled via a reusable enrollment token (see
    AgentEnrollView) is actually legitimate — until this, every agent-facing
    endpoint 401s for it (DeviceTokenAuthentication.authenticate())."""

    permission_classes = [IsAuthenticated, HasPermission("device.disable")]

    def post(self, request, device_id):
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        device.is_approved = True
        device.save(update_fields=["is_approved"])
        log_action(
            user=request.user, action="device.approved", device_id=device.device_id, request=request
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


class AssetSyncView(APIView):
    """Called by the separate asset_dfm system, not the dashboard or the
    agent — machine-to-machine, so it's a shared API key (X-Api-Key header)
    rather than the JWT/device-token auth every other endpoint here uses.
    AllowAny at the DRF level is correct: the real check happens inside
    post() itself, same pattern as AgentEnrollView's own token check above.

    asset_dfm tracks every asset category (PC, laptop, monitor, printer,
    UPS, ...) through this same insert/update code path, but a SentinelDesk
    Device IS a laptop - a printer or monitor can never correspond to one,
    so there's nothing useful to match or show on the Assets page for it.
    asset_code's own format already encodes the category as its first 3
    digits (see ASSET_CODE_VALIDATOR) - "302" is Laptop (see asset_dfm's own
    kategori_asset table) - so this is skipped here rather than asking
    asset_dfm's PHP side to filter before calling, keeping that decision in
    one place. Still 200, not an error: this is normal, expected traffic
    asset_dfm sends for every asset it has, not a problem to report."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "asset_sync"

    LAPTOP_CATEGORY_CODE = "302"
    # asset_dfm's own "302" category code means Laptop, but it's filed by
    # whoever enters the data by hand on their side - confirmed live, a
    # printer (302-25031-01, "Printer Hp 108w") was mis-filed under "302"
    # anyway, so the code-prefix check above isn't actually sufficient on
    # its own. This is a second check against the free-text item name as a
    # safety net - never perfect, but catches the mistake the code alone
    # can't.
    NON_LAPTOP_NAME_KEYWORDS = ("printer", "monitor", "proyektor", "projector", "scanner", "ups")

    def post(self, request):
        provided_key = request.META.get("HTTP_X_API_KEY", "")
        if not settings.ASSET_SYNC_API_KEY or provided_key != settings.ASSET_SYNC_API_KEY:
            return Response({"detail": "Invalid or missing API key."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = AssetSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not data["asset_code"].startswith(f"{self.LAPTOP_CATEGORY_CODE}-"):
            return Response({"detail": "Skipped: not a laptop-category asset.", "skipped": True})

        nama_aset_lower = data["nama_aset"].lower()
        if any(keyword in nama_aset_lower for keyword in self.NON_LAPTOP_NAME_KEYWORDS):
            return Response({"detail": "Skipped: item name indicates a non-laptop asset.", "skipped": True})

        asset = sync_asset(
            asset_code=data["asset_code"],
            kondisi=data["kondisi"],
            status_barang=data["status_barang"],
            penanggung_jawab=data["penanggung_jawab"],
            lokasi=data["lokasi"],
            nama_aset=data["nama_aset"],
            merk=data["merk"],
            spesifikasi=data["spesifikasi"],
            lokasi_detail=data["lokasi_detail"],
        )
        log_action(
            action="asset.synced",
            request=request,
            metadata={"asset_code": asset.asset_code, "match_status": asset.match_status},
        )
        return Response(AssetSerializer(asset).data, status=status.HTTP_200_OK)


class AssetListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("device.view")]
    serializer_class = AssetSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["match_status", "kondisi", "status_barang"]
    search_fields = ["asset_code", "raw_penanggung_jawab", "raw_lokasi", "nama_aset", "merk"]
    queryset = Asset.objects.select_related(
        "device", "device__assigned_employee", "device__branch",
        "suggested_device", "suggested_device__assigned_employee",
        "current_employee",
    ).all()


class AssetLinkView(APIView):
    """Manually set (or clear) which Device an Asset belongs to — the admin
    review step for anything the auto-matcher left as NEEDS_REVIEW or
    UNLINKED (see asset_matching.py), and also how to correct a wrong
    AUTO_MATCHED link. Once set here the asset is pinned to LINKED_MANUALLY,
    which sync_asset() never overwrites on a later asset_dfm sync."""

    permission_classes = [IsAuthenticated, HasPermission("device.manage")]

    def post(self, request, pk):
        try:
            asset = Asset.objects.get(pk=pk)
        except Asset.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = serializer.validated_data["device_id"]

        if device and asset.kondisi != Asset.Condition.BAIK:
            # Mirrors sync_asset()'s own rule (see asset_matching.py) - a
            # damaged/lost/retired unit can't be the laptop behind any
            # active Device, so this is blocked here too, not just left to
            # the next sync to quietly fix.
            return Response(
                {"detail": f"Asset ini berstatus kondisi '{asset.kondisi}' - tidak bisa ditautkan ke device aktif."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if device:
            # Asset.device is a ForeignKey, not OneToOne, on purpose - one
            # employee can legitimately have more than one laptop asset
            # pointing at the same device over time (a retired one left as
            # Kondisi=Dihapus/Hilang, a replacement issued). But two ACTIVE
            # laptop records both claiming the same physical device at once
            # is never legitimate - almost always a manual-link mistake
            # (easy to make when picking between near-identical spare
            # laptops, e.g. two "IT" devices with no distinguishing name) -
            # so that specific case is blocked here rather than silently
            # allowed through.
            conflicting = device.assets.exclude(pk=asset.pk).exclude(
                kondisi__in=[Asset.Condition.HILANG, Asset.Condition.DIHAPUS]
            )
            if conflicting.exists():
                other = conflicting.first()
                return Response(
                    {
                        "detail": (
                            f"Device {device.device_id} sudah tertaut ke asset aktif lain "
                            f"({other.asset_code}). Lepas tautan itu dulu (atau tandai Hilang/Dihapus) "
                            "sebelum menautkan ke asset ini."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        asset.device = device
        asset.match_status = Asset.MatchStatus.LINKED_MANUALLY if device else Asset.MatchStatus.UNLINKED
        asset.match_confidence = None
        asset.save(update_fields=["device", "match_status", "match_confidence"])

        # Convenience pre-fill, same spirit as sync_asset()'s own - a
        # device picked via the spec-based suggestions (see
        # DeviceAssetSuggestionsView) has no assigned_employee at all yet
        # by definition, so without this, linking the right asset still
        # leaves the device looking blank. Never overwrites an employee
        # that's already set - this only fires the first time.
        if device and not device.assigned_employee_id:
            employee = find_employee_by_name(asset.raw_penanggung_jawab)
            if employee:
                device.assigned_employee = employee
                device.save(update_fields=["assigned_employee"])
                asset.current_employee = employee
                asset.user_status = Asset.UserStatus.IDENTIFIED
                asset.save(update_fields=["current_employee", "user_status"])

        log_action(
            user=request.user,
            action="asset.linked_manually",
            request=request,
            metadata={"asset_code": asset.asset_code, "device_id": device.device_id if device else None},
        )
        return Response(AssetSerializer(asset).data)


class AssetSetUserView(APIView):
    """Sets (or clears) who's actually using an asset right now - see
    Asset.current_employee's docstring. Deliberately separate from
    AssetLinkView above: this never touches `device`/match_status at all
    and works for any asset regardless of whether its laptop has
    SentinelDesk installed, which is exactly the point - a laptop swap
    between employees is recorded here in one click, with no dependency on
    SentinelDesk device-matching succeeding first."""

    permission_classes = [IsAuthenticated, HasPermission("device.manage")]

    def post(self, request, pk):
        try:
            asset = Asset.objects.get(pk=pk)
        except Asset.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetSetUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.validated_data["employee"]

        asset.current_employee = employee
        # Keep user_status in step with the admin's own explicit decision -
        # setting a name here is as confident an answer as classify_user()
        # itself gives (IDENTIFIED), and clearing it back to "nobody" is
        # the same real-world state as a genuine unassigned/pool asset
        # (INCOMPLETE, same bucket "IT"-labeled spares land in - see
        # classify_user()) even though raw_penanggung_jawab's text is
        # untouched and might still literally name someone: the admin is
        # the more trustworthy, more current signal here, e.g. right after
        # recording a laptop swap where the old holder gave this one back.
        asset.user_status = Asset.UserStatus.IDENTIFIED if employee else Asset.UserStatus.INCOMPLETE
        asset.save(update_fields=["current_employee", "user_status"])

        # Keep the linked Device's own org assignment in step with this -
        # Asset.current_employee and Device.assigned_employee both describe
        # "who's actually holding this physical laptop right now", just
        # recorded in two different places for two different reasons (see
        # Asset.current_employee's docstring). A laptop swap recorded here
        # should show up immediately on the Device side too (alerts,
        # Devices list, the auto-matcher's own signal for OTHER assets),
        # not require a second manual edit on Device Detail. Only cascades
        # when there IS a linked device - most assets don't have one yet.
        if asset.device_id and employee:
            device = asset.device
            device.assigned_employee = employee
            update_fields = ["assigned_employee"]
            if employee.department_id:
                device.department = employee.department
                device.branch = employee.department.branch
                device.company = employee.department.branch.company
                update_fields += ["department", "branch", "company"]
            device.save(update_fields=update_fields)
        elif asset.device_id and not employee:
            # Clearing the asset's user doesn't erase the device's own org
            # assignment (company/branch/department) - only the
            # employee-level "who", which is the actual single source of
            # ambiguity a clear is meant to express.
            asset.device.assigned_employee = None
            asset.device.save(update_fields=["assigned_employee"])

        log_action(
            user=request.user,
            action="asset.user_set",
            request=request,
            metadata={"asset_code": asset.asset_code, "employee_id": employee.id if employee else None},
        )
        return Response(AssetSerializer(asset).data)


class DeviceRotateTokenView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("agent.manage")]

    def post(self, request, device_id):
        device = get_object_or_404(Device, device_id=device_id)
        new_raw_token = DeviceCredential.generate_token()
        cred, _ = DeviceCredential.objects.get_or_create(device=device)
        cred.token_hash = make_password(new_raw_token)
        cred.save(update_fields=["token_hash"])

        log_action(
            user=request.user,
            action="device.token_rotated",
            request=request,
            device_id=device.device_id,
            metadata={"device_id": device.device_id},
        )
        return Response(
            {
                "device_id": device.device_id,
                "device_token": new_raw_token,
                "message": "Token perangkat berhasil dirotasi.",
            },
            status=status.HTTP_200_OK,
        )


class AgentRotateTokenView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        device: Device = request.auth
        new_raw_token = DeviceCredential.generate_token()
        cred = device.credential
        cred.token_hash = make_password(new_raw_token)
        cred.save(update_fields=["token_hash"])

        log_action(
            action="agent.token_rotated",
            device_id=device.device_id,
            metadata={"device_id": device.device_id, "by": "agent"},
        )
        return Response(
            {
                "device_id": device.device_id,
                "device_token": new_raw_token,
            },
            status=status.HTTP_200_OK,
        )
