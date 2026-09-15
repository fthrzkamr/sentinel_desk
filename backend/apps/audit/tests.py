import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.audit.services import log_action


@pytest.fixture
def auditor_role(db):
    role = Role.objects.create(name="AUDITOR")
    role.permissions.set([Permission.objects.get_or_create(code="audit.view")[0]])
    return role


@pytest.fixture
def no_perm_role(db):
    return Role.objects.create(name="NO_PERMS")


@pytest.fixture
def auditor_user(db, auditor_role):
    return User.objects.create_user(
        username="auditor", email="auditor@example.com", password="StrongPass123!", role=auditor_role
    )


@pytest.fixture
def no_perm_user(db, no_perm_role):
    return User.objects.create_user(
        username="noperm", email="noperm@example.com", password="StrongPass123!", role=no_perm_role
    )


def _client_for(username):
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.mark.django_db
def test_audit_log_list_requires_permission(auditor_user, no_perm_user):
    log_action(user=auditor_user, action="device.disabled", device_id="SD-LPT-000001", metadata={"reason": "test"})

    denied = _client_for("noperm").get("/api/audit-logs/")
    assert denied.status_code == 403

    allowed = _client_for("auditor").get("/api/audit-logs/")
    assert allowed.status_code == 200
    assert allowed.data["count"] >= 1


@pytest.mark.django_db
def test_audit_log_filter_by_action(auditor_user):
    log_action(user=auditor_user, action="device.disabled", device_id="SD-LPT-000001")
    log_action(user=auditor_user, action="device.enabled", device_id="SD-LPT-000001")

    client = _client_for("auditor")
    response = client.get("/api/audit-logs/?action=device.disabled")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["action"] == "device.disabled"


@pytest.mark.django_db
def test_audit_log_search_by_device_id(auditor_user):
    log_action(user=auditor_user, action="device.disabled", device_id="SD-LPT-000042")
    log_action(user=auditor_user, action="device.disabled", device_id="SD-LPT-000099")

    client = _client_for("auditor")
    response = client.get("/api/audit-logs/?search=000042")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["device_id"] == "SD-LPT-000042"


@pytest.mark.django_db
def test_audit_log_is_read_only_over_the_api(auditor_user):
    client = _client_for("auditor")
    response = client.post("/api/audit-logs/", {"action": "fake"}, format="json")
    assert response.status_code == 405
