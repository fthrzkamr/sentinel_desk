import re

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.audit.models import AuditLog
from apps.devices.models import (
    Branch,
    Company,
    Department,
    Device,
    DeviceCredential,
    Employee,
    EnrollmentToken,
)


@pytest.fixture
def agent_manage_role(db):
    role = Role.objects.create(name="IT_ADMIN_TEST")
    perms = Permission.objects.bulk_create(
        [
            Permission(code="agent.manage"),
            Permission(code="device.view"),
            Permission(code="device.disable"),
            Permission(code="software.manage"),
        ]
    )
    role.permissions.set(perms)
    return role


@pytest.fixture
def admin_user(db, agent_manage_role):
    return User.objects.create_user(
        username="itadmin", email="itadmin@example.com", password="StrongPass123!", role=agent_manage_role
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    login = client.post(
        "/api/auth/login/", {"username": "itadmin", "password": "StrongPass123!"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.fixture
def enrollment_token(admin_user):
    token, raw = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60, label="test")
    return token, raw


@pytest.mark.django_db
def test_create_enrollment_token_requires_permission(admin_client):
    response = admin_client.post("/api/agent/enrollment-tokens/", {"label": "laptop-a"}, format="json")

    assert response.status_code == 201
    assert "token" in response.data
    assert EnrollmentToken.objects.count() == 1


@pytest.mark.django_db
def test_enroll_with_valid_token_creates_device(enrollment_token):
    _, raw_token = enrollment_token
    client = APIClient()

    response = client.post(
        "/api/agent/enroll/",
        {"token": raw_token, "hostname": "LAPTOP-TEST", "os_name": "Windows"},
        format="json",
    )

    assert response.status_code == 201
    # Not a literal "SD-LPT-000001": device_id is derived from the Device
    # table's PK sequence, which Postgres never rolls back even between
    # test transactions — only the format is guaranteed, not the number.
    assert re.fullmatch(r"SD-LPT-\d{6}", response.data["device_id"])
    assert "device_token" in response.data

    device = Device.objects.get(device_id=response.data["device_id"])
    assert device.hostname == "LAPTOP-TEST"
    assert device.status == Device.Status.OFFLINE
    assert DeviceCredential.objects.filter(device=device).exists()
    assert AuditLog.objects.filter(action="device.registered", device_id=response.data["device_id"]).exists()


@pytest.mark.django_db
def test_reenroll_with_same_mac_reuses_existing_device(admin_user):
    first_token, first_raw = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    client = APIClient()

    first_response = client.post(
        "/api/agent/enroll/",
        {"token": first_raw, "hostname": "LAPTOP-OLD", "mac_address": "AA:BB:CC:DD:EE:FF"},
        format="json",
    )
    assert first_response.status_code == 201
    original_device_id = first_response.data["device_id"]
    original_token = DeviceCredential.objects.get(device__device_id=original_device_id).token_hash

    # Laptop gets wiped and the agent reinstalled with a brand new
    # enrollment token — same physical hardware, same MAC address.
    second_token, second_raw = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    second_response = client.post(
        "/api/agent/enroll/",
        {"token": second_raw, "hostname": "LAPTOP-NEW-NAME", "mac_address": "AA:BB:CC:DD:EE:FF"},
        format="json",
    )

    assert second_response.status_code == 201
    assert second_response.data["device_id"] == original_device_id
    assert Device.objects.filter(mac_address="AA:BB:CC:DD:EE:FF").count() == 1

    device = Device.objects.get(device_id=original_device_id)
    assert device.hostname == "LAPTOP-NEW-NAME"
    assert device.status == Device.Status.OFFLINE

    # Old device token must no longer work — it was rotated, not duplicated.
    assert DeviceCredential.objects.filter(device=device).count() == 1
    assert DeviceCredential.objects.get(device=device).token_hash != original_token
    assert AuditLog.objects.filter(action="device.reenrolled", device_id=original_device_id).exists()


@pytest.mark.django_db
def test_enroll_with_blank_mac_never_dedups(admin_user):
    for hostname in ["LAPTOP-A", "LAPTOP-B"]:
        token, raw = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
        APIClient().post("/api/agent/enroll/", {"token": raw, "hostname": hostname}, format="json")

    assert Device.objects.count() == 2


@pytest.mark.django_db
def test_enrollment_token_is_single_use(enrollment_token):
    _, raw_token = enrollment_token
    client = APIClient()
    client.post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-A"}, format="json")

    response = client.post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-B"}, format="json")

    assert response.status_code == 401
    assert Device.objects.count() == 1


@pytest.mark.django_db
def test_enroll_with_expired_token_is_rejected(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    token.expires_at = timezone.now() - timezone.timedelta(minutes=1)
    token.save(update_fields=["expires_at"])

    response = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-A"}, format="json"
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_heartbeat_updates_status_and_last_seen(enrollment_token):
    _, raw_token = enrollment_token
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-TEST"}, format="json"
    )
    device_id = enroll_resp.data["device_id"]
    device_token = enroll_resp.data["device_token"]

    client = APIClient()
    response = client.post(
        "/api/agent/heartbeat/",
        {"agent_version": "0.1.0"},
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )

    assert response.status_code == 200
    assert response.data["status"] == "ONLINE"

    device = Device.objects.get(device_id=device_id)
    assert device.status == Device.Status.ONLINE
    assert device.last_seen is not None
    assert device.agent_version == "0.1.0"


@pytest.mark.django_db
def test_heartbeat_with_invalid_token_is_rejected(enrollment_token):
    _, raw_token = enrollment_token
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-TEST"}, format="json"
    )
    device_id = enroll_resp.data["device_id"]

    response = APIClient().post(
        "/api/agent/heartbeat/",
        {},
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION="DeviceToken wrong-token",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_disabled_device_cannot_heartbeat(admin_client, enrollment_token):
    _, raw_token = enrollment_token
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-TEST"}, format="json"
    )
    device_id = enroll_resp.data["device_id"]
    device_token = enroll_resp.data["device_token"]

    disable_resp = admin_client.post(f"/api/devices/{device_id}/disable/")
    assert disable_resp.status_code == 200
    assert disable_resp.data["status"] == "DISABLED"

    response = APIClient().post(
        "/api/agent/heartbeat/",
        {},
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_viewer_role_cannot_disable_device(db, enrollment_token):
    viewer_role = Role.objects.create(name="VIEWER_TEST")
    viewer_role.permissions.set([Permission.objects.get_or_create(code="device.view")[0]])
    viewer = User.objects.create_user(
        username="viewer", email="viewer@example.com", password="StrongPass123!", role=viewer_role
    )
    viewer_client = APIClient()
    login = viewer_client.post(
        "/api/auth/login/", {"username": "viewer", "password": "StrongPass123!"}, format="json"
    )
    viewer_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    _, raw_token = enrollment_token
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-TEST"}, format="json"
    )
    device_id = enroll_resp.data["device_id"]

    response = viewer_client.post(f"/api/devices/{device_id}/disable/")

    assert response.status_code == 403


@pytest.fixture
def org_manager_role(db):
    role = Role.objects.create(name="ORG_MANAGER_TEST")
    role.permissions.set([Permission.objects.get_or_create(code="device.manage")[0]])
    return role


@pytest.fixture
def org_manager_user(db, org_manager_role):
    return User.objects.create_user(
        username="orgmanager", email="orgmanager@example.com", password="StrongPass123!", role=org_manager_role
    )


def _client_for(username):
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.fixture
def org_tree(db):
    company = Company.objects.create(name="Acme Corp")
    branch = Branch.objects.create(company=company, name="Jakarta")
    department = Department.objects.create(branch=branch, name="IT")
    employee = Employee.objects.create(department=department, full_name="Budi Santoso")
    return company, branch, department, employee


@pytest.mark.django_db
def test_org_crud_requires_device_manage_permission(org_manager_user, admin_user):
    manager_client = _client_for("orgmanager")
    plain_client = _client_for("itadmin")  # agent_manage_role, no device.manage

    create = manager_client.post("/api/companies/", {"name": "Acme Corp"}, format="json")
    assert create.status_code == 201

    denied = plain_client.post("/api/companies/", {"name": "Should Fail"}, format="json")
    assert denied.status_code == 403


@pytest.mark.django_db
def test_branch_department_employee_cascade_and_filter(org_manager_user, org_tree):
    company, branch, department, employee = org_tree
    client = _client_for("orgmanager")

    other_company = Company.objects.create(name="Other Co")
    Branch.objects.create(company=other_company, name="Bandung")

    response = client.get(f"/api/branches/?company={company.id}")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["name"] == "Jakarta"

    dept_response = client.get(f"/api/departments/?branch={branch.id}")
    assert dept_response.data["count"] == 1

    emp_response = client.get(f"/api/employees/?department={department.id}")
    assert emp_response.data["count"] == 1
    assert emp_response.data["results"][0]["full_name"] == "Budi Santoso"


@pytest.mark.django_db
def test_enrollment_token_with_org_assignment_applies_to_device(admin_user, org_tree):
    company, branch, department, employee = org_tree
    client = _client_for("itadmin")

    create = client.post(
        "/api/agent/enrollment-tokens/",
        {
            "label": "laptop-budi",
            "ttl_minutes": 30,
            "company": company.id,
            "branch": branch.id,
            "department": department.id,
            "assigned_employee": employee.id,
        },
        format="json",
    )
    assert create.status_code == 201
    raw_token = create.data["token"]

    enroll_response = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-BUDI"}, format="json"
    )
    assert enroll_response.status_code == 201

    device = Device.objects.get(device_id=enroll_response.data["device_id"])
    assert device.company_id == company.id
    assert device.branch_id == branch.id
    assert device.department_id == department.id
    assert device.assigned_employee_id == employee.id


@pytest.mark.django_db
def test_enrollment_token_without_org_assignment_leaves_device_unassigned(admin_user, enrollment_token):
    _, raw_token = enrollment_token
    enroll_response = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-PLAIN"}, format="json"
    )
    device = Device.objects.get(device_id=enroll_response.data["device_id"])
    assert device.company_id is None
    assert device.branch_id is None


@pytest.mark.django_db
def test_device_view_only_role_cannot_edit_org_assignment(admin_user, enrollment_token, org_tree):
    company, branch, department, employee = org_tree
    _, raw_token = enrollment_token
    enroll_resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-EDIT"}, format="json")
    device_id = enroll_resp.data["device_id"]

    view_only_role = Role.objects.create(name="VIEW_ONLY_TEST")
    view_only_role.permissions.set([Permission.objects.get_or_create(code="device.view")[0]])
    User.objects.create_user(
        username="viewonly", email="viewonly@example.com", password="StrongPass123!", role=view_only_role
    )
    client = _client_for("viewonly")

    get_response = client.get(f"/api/devices/{device_id}/")
    assert get_response.status_code == 200

    patch_response = client.patch(f"/api/devices/{device_id}/", {"company": company.id}, format="json")
    assert patch_response.status_code == 403


@pytest.mark.django_db
def test_device_manage_role_can_edit_org_assignment(org_manager_user, enrollment_token, org_tree):
    company, branch, department, employee = org_tree
    _, raw_token = enrollment_token
    enroll_resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-EDIT-2"}, format="json")
    device_id = enroll_resp.data["device_id"]

    client = _client_for("orgmanager")
    response = client.patch(
        f"/api/devices/{device_id}/",
        {"company": company.id, "branch": branch.id, "department": department.id, "assigned_employee": employee.id},
        format="json",
    )
    assert response.status_code == 200

    device = Device.objects.get(device_id=device_id)
    assert device.company_id == company.id
    assert device.assigned_employee_id == employee.id
    assert AuditLog.objects.filter(action="device.updated", user=org_manager_user).exists()


@pytest.mark.django_db
def test_device_org_assignment_can_be_cleared(org_manager_user, enrollment_token, org_tree):
    company, branch, department, employee = org_tree
    _, raw_token = enrollment_token
    enroll_resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-EDIT-3"}, format="json")
    device_id = enroll_resp.data["device_id"]

    client = _client_for("orgmanager")
    client.patch(f"/api/devices/{device_id}/", {"company": company.id}, format="json")

    clear_response = client.patch(f"/api/devices/{device_id}/", {"company": None}, format="json")
    assert clear_response.status_code == 200
    device = Device.objects.get(device_id=device_id)
    assert device.company_id is None


@pytest.mark.django_db
def test_agent_endpoints_reject_missing_device_auth():
    assert APIClient().post("/api/agent/heartbeat/", {}, format="json").status_code == 401


# --- Reusable enrollment tokens + pending-approval devices ---


@pytest.mark.django_db
def test_normal_token_enrolled_device_is_approved_immediately(enrollment_token):
    _, raw_token = enrollment_token
    response = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-NORMAL"}, format="json"
    )

    device = Device.objects.get(device_id=response.data["device_id"])
    assert device.is_approved is True


@pytest.mark.django_db
def test_reusable_token_enrolled_device_starts_pending_approval(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60, is_reusable=True)

    response = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-PENDING"}, format="json"
    )

    assert response.status_code == 201
    device = Device.objects.get(device_id=response.data["device_id"])
    assert device.is_approved is False


@pytest.mark.django_db
def test_auto_enroll_without_token_starts_pending_approval():
    # Tokenless auto-registration: agent passes empty token or omits it entirely
    response = APIClient().post(
        "/api/agent/enroll/",
        {"hostname": "AUTO-LAPTOP-01", "os_name": "Windows 11", "mac_address": "CC:DD:EE:11:22:33"},
        format="json",
    )

    assert response.status_code == 201
    assert "device_id" in response.data
    assert "device_token" in response.data

    device = Device.objects.get(device_id=response.data["device_id"])
    assert device.hostname == "AUTO-LAPTOP-01"
    assert device.is_approved is False
    assert device.status == Device.Status.OFFLINE
    assert DeviceCredential.objects.filter(device=device).exists()
    assert AuditLog.objects.filter(action="device.registered", device_id=device.device_id).exists()


@pytest.mark.django_db
def test_reusable_token_enrolls_multiple_devices_without_being_consumed(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60, is_reusable=True)

    first = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-A"}, format="json")
    second = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-B"}, format="json")

    assert first.status_code == 201
    assert second.status_code == 201
    assert Device.objects.count() == 2

    token.refresh_from_db()
    assert token.used_at is None  # never "spent", unlike a single-use token
    assert token.use_count == 2
    assert token.is_valid  # still usable for a third device


@pytest.mark.django_db
def test_pending_device_cannot_use_agent_endpoints_until_approved(admin_user):
    _, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60, is_reusable=True)
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-PENDING"}, format="json"
    )
    device_id, device_token = enroll_resp.data["device_id"], enroll_resp.data["device_token"]

    blocked = APIClient().post(
        "/api/agent/heartbeat/", {}, format="json", HTTP_X_DEVICE_ID=device_id, HTTP_AUTHORIZATION=f"DeviceToken {device_token}"
    )
    assert blocked.status_code == 401

    device = Device.objects.get(device_id=device_id)
    device.is_approved = True
    device.save(update_fields=["is_approved"])

    allowed = APIClient().post(
        "/api/agent/heartbeat/", {}, format="json", HTTP_X_DEVICE_ID=device_id, HTTP_AUTHORIZATION=f"DeviceToken {device_token}"
    )
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_approve_endpoint_flips_flag_and_requires_permission(admin_client, admin_user):
    _, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60, is_reusable=True)
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-PENDING"}, format="json"
    )
    device_id = enroll_resp.data["device_id"]

    no_perm_role = Role.objects.create(name="NO_APPROVE_PERM")
    no_perm_user = User.objects.create_user(
        username="no_approve", email="no_approve@example.com", password="StrongPass123!", role=no_perm_role
    )
    no_perm_client = APIClient()
    login = no_perm_client.post(
        "/api/auth/login/", {"username": "no_approve", "password": "StrongPass123!"}, format="json"
    )
    no_perm_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    denied = no_perm_client.post(f"/api/devices/{device_id}/approve/")
    assert denied.status_code == 403
    assert Device.objects.get(device_id=device_id).is_approved is False

    approved = admin_client.post(f"/api/devices/{device_id}/approve/")
    assert approved.status_code == 200
    assert Device.objects.get(device_id=device_id).is_approved is True
    assert AuditLog.objects.filter(action="device.approved", device_id=device_id).exists()


@pytest.mark.django_db
def test_dashboard_summary_returns_counts_compliance_and_high_risk_devices(admin_client):
    from apps.alerts.models import Alert

    compliant_device = Device.objects.create(
        device_id="SD-LPT-000101",
        hostname="LAPTOP-COMPLIANT",
        status=Device.Status.ONLINE,
        is_approved=True,
        bitlocker_enabled=True,
        firewall_enabled=True,
        antivirus_enabled=True,
        battery_design_capacity_mwh=50000,
        battery_full_charge_capacity_mwh=45000,
    )
    risky_device = Device.objects.create(
        device_id="SD-LPT-000102",
        hostname="LAPTOP-RISKY",
        status=Device.Status.CRITICAL,
        is_approved=False,
        bitlocker_enabled=False,
        firewall_enabled=False,
        antivirus_enabled=False,
        battery_design_capacity_mwh=50000,
        battery_full_charge_capacity_mwh=20000,
    )
    Device.objects.create(
        device_id="SD-LPT-000103",
        hostname="LAPTOP-DISABLED",
        status=Device.Status.DISABLED,
        is_approved=True,
        bitlocker_enabled=False,
        firewall_enabled=False,
        antivirus_enabled=False,
    )

    Alert.objects.create(
        device=risky_device,
        category=Alert.Category.DATA_EXFIL,
        severity=Alert.Severity.CRITICAL,
        message="Exfil alert",
    )

    response = admin_client.get("/api/devices/dashboard-summary/")
    assert response.status_code == 200

    status_counts = response.data["status_counts"]
    assert status_counts["total"] == 3
    assert status_counts["ONLINE"] == 1
    assert status_counts["CRITICAL"] == 1
    assert status_counts["DISABLED"] == 1
    assert status_counts["pending_approval"] == 1

    compliance = response.data["compliance"]
    assert compliance["active_total"] == 2  # excludes DISABLED
    assert compliance["fully_compliant"] == 1
    assert compliance["bitlocker_off"] == 1
    assert compliance["firewall_off"] == 1
    assert compliance["antivirus_off"] == 1
    assert compliance["low_battery_health"] == 1

    high_risk = response.data["high_risk_devices"]
    assert len(high_risk) == 1
    assert high_risk[0]["device_id"] == risky_device.device_id
    assert high_risk[0]["score"] > 0
    assert high_risk[0]["device_id"] != compliant_device.device_id


@pytest.mark.django_db
def test_heartbeat_and_metrics_deliver_remote_policy_and_ota_download(enrollment_token, tmp_path, settings):
    import os
    from apps.system_settings.models import SystemSettings

    settings.MEDIA_ROOT = tmp_path

    # Configure solo settings with custom remote policy and OTA
    solo = SystemSettings.get_solo()
    solo.agent_metrics_interval_seconds = 20
    solo.agent_screen_monitor_enabled = True
    solo.agent_usb_monitor_enabled = False
    solo.agent_auto_update_enabled = True
    solo.agent_latest_version = "0.8.16"
    solo.agent_download_url = "/api/agent/download/0.8.16/"
    solo.agent_sha256 = "dummyhash123"
    solo.save()

    _, raw_token = enrollment_token
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-POLICY-TEST"}, format="json"
    )
    device_id = enroll_resp.data["device_id"]
    device_token = enroll_resp.data["device_token"]

    client = APIClient()
    # 1. Heartbeat receives policy & update info
    hb_resp = client.post(
        "/api/agent/heartbeat/",
        {"agent_version": "0.8.15"},
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )
    assert hb_resp.status_code == 200
    assert "policy" in hb_resp.data
    assert hb_resp.data["policy"]["metrics_interval_seconds"] == 20
    assert hb_resp.data["policy"]["usb_monitor_enabled"] is False

    assert "update" in hb_resp.data
    assert hb_resp.data["update"]["latest_version"] == "0.8.16"
    assert hb_resp.data["update"]["sha256"] == "dummyhash123"

    # 2. Metrics receives policy & update info as well
    metric_resp = client.post(
        "/api/agent/metrics/",
        {"cpu_percent": 15, "ram_percent": 30, "disk_percent": 40},
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )
    assert metric_resp.status_code == 201
    assert "policy" in metric_resp.data
    assert metric_resp.data["policy"]["metrics_interval_seconds"] == 20

    # 3. Test AgentDownloadView
    dest_dir = tmp_path / "agent"
    os.makedirs(dest_dir, exist_ok=True)
    binary_file = dest_dir / "SentinelDeskAgent-0.8.16.exe"
    binary_file.write_bytes(b"FakeAgentBinaryForTesting")

    dl_resp = client.get(
        "/api/agent/download/0.8.16/",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )
    assert dl_resp.status_code == 200
    assert b"".join(dl_resp.streaming_content) == b"FakeAgentBinaryForTesting"


@pytest.mark.django_db
def test_device_token_rotation_by_admin_and_agent(admin_client, enrollment_token):
    _, raw_token = enrollment_token
    enroll_resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-ROTATE"}, format="json"
    )
    device_id = enroll_resp.data["device_id"]
    initial_device_token = enroll_resp.data["device_token"]

    # 1. Admin rotates token
    rotate_resp = admin_client.post(f"/api/devices/{device_id}/rotate-token/")
    assert rotate_resp.status_code == 200
    new_token_1 = rotate_resp.data["device_token"]
    assert new_token_1 != initial_device_token
    assert AuditLog.objects.filter(action="device.token_rotated", device_id=device_id).exists()

    # Old token no longer works
    client = APIClient()
    hb_fail = client.post(
        "/api/agent/heartbeat/",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {initial_device_token}",
    )
    assert hb_fail.status_code == 401

    # New token works
    hb_ok = client.post(
        "/api/agent/heartbeat/",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {new_token_1}",
    )
    assert hb_ok.status_code == 200

    # 2. Agent rotates own token
    agent_rotate_resp = client.post(
        "/api/agent/rotate-token/",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {new_token_1}",
    )
    assert agent_rotate_resp.status_code == 200
    new_token_2 = agent_rotate_resp.data["device_token"]
    assert new_token_2 != new_token_1

    # Now new_token_2 works
    hb_ok2 = client.post(
        "/api/agent/heartbeat/",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {new_token_2}",
    )
    assert hb_ok2.status_code == 200



