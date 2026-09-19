import hashlib
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.audit.models import AuditLog
from apps.devices.models import AgentRelease, Branch, Company, Department, Device, DeviceCredential, Employee, EnrollmentToken


@pytest.fixture
def agent_manage_role(db):
    role = Role.objects.create(name="IT_ADMIN_TEST")
    perms = Permission.objects.bulk_create(
        [
            Permission(code="agent.manage"),
            Permission(code="device.view"),
            Permission(code="device.disable"),
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


# --- Agent self-update ---


def _enrolled_device_credentials(raw_token):
    resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-UPDATE"}, format="json")
    return resp.data["device_id"], resp.data["device_token"]


def _agent_get(device_id, device_token, path):
    return APIClient().get(path, HTTP_X_DEVICE_ID=device_id, HTTP_AUTHORIZATION=f"DeviceToken {device_token}")


@pytest.mark.django_db
def test_uploading_release_computes_sha256_and_only_one_stays_active(admin_client):
    content_a = b"fake-exe-bytes-v1"
    resp_a = admin_client.post(
        "/api/agent-releases/",
        {"version": "0.2.0", "is_active": True, "exe_file": SimpleUploadedFile("agent.exe", content_a)},
        format="multipart",
    )
    assert resp_a.status_code == 201
    assert resp_a.data["sha256"] == hashlib.sha256(content_a).hexdigest()
    assert resp_a.data["file_size"] == len(content_a)

    content_b = b"fake-exe-bytes-v2-longer"
    resp_b = admin_client.post(
        "/api/agent-releases/",
        {"version": "0.3.0", "is_active": True, "exe_file": SimpleUploadedFile("agent.exe", content_b)},
        format="multipart",
    )
    assert resp_b.status_code == 201

    release_a = AgentRelease.objects.get(version="0.2.0")
    release_b = AgentRelease.objects.get(version="0.3.0")
    assert release_a.is_active is False
    assert release_b.is_active is True


@pytest.mark.django_db
def test_release_upload_requires_agent_manage_permission():
    response = APIClient().post(
        "/api/agent-releases/",
        {"version": "0.2.0", "exe_file": SimpleUploadedFile("agent.exe", b"x")},
        format="multipart",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_agent_version_check_returns_active_release(admin_client, enrollment_token):
    _, raw_token = enrollment_token
    device_id, device_token = _enrolled_device_credentials(raw_token)

    content = b"fake-exe-bytes"
    admin_client.post(
        "/api/agent-releases/",
        {"version": "0.5.0", "is_active": True, "exe_file": SimpleUploadedFile("agent.exe", content)},
        format="multipart",
    )

    response = _agent_get(device_id, device_token, "/api/agent/version/")
    assert response.status_code == 200
    assert response.data["version"] == "0.5.0"
    assert response.data["sha256"] == hashlib.sha256(content).hexdigest()
    assert response.data["file_size"] == len(content)


@pytest.mark.django_db
def test_agent_version_check_404_when_no_active_release(enrollment_token):
    _, raw_token = enrollment_token
    device_id, device_token = _enrolled_device_credentials(raw_token)

    response = _agent_get(device_id, device_token, "/api/agent/version/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_agent_download_streams_exact_bytes_and_is_logged(admin_client, enrollment_token):
    _, raw_token = enrollment_token
    device_id, device_token = _enrolled_device_credentials(raw_token)

    content = b"fake-exe-bytes-for-download-test"
    admin_client.post(
        "/api/agent-releases/",
        {"version": "0.6.0", "is_active": True, "exe_file": SimpleUploadedFile("agent.exe", content)},
        format="multipart",
    )

    response = _agent_get(device_id, device_token, "/api/agent/download/")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == content
    assert AuditLog.objects.filter(action="agent.update_downloaded", device_id=device_id).exists()


@pytest.mark.django_db
def test_agent_endpoints_reject_missing_device_auth():
    assert APIClient().get("/api/agent/version/").status_code == 401
    assert APIClient().get("/api/agent/download/").status_code == 401
