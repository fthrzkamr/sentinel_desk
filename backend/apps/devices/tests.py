import re

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.audit.models import AuditLog
from apps.devices.models import Device, DeviceCredential, EnrollmentToken


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
