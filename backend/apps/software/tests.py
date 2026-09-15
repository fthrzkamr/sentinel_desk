import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.devices.models import EnrollmentToken
from apps.software.models import Software


@pytest.fixture
def software_role(db):
    role = Role.objects.create(name="SOFTWARE_TEST")
    role.permissions.set([Permission.objects.create(code="software.view")])
    return role


@pytest.fixture
def admin_user(db, software_role):
    return User.objects.create_user(
        username="sw_admin", email="sw_admin@example.com", password="StrongPass123!", role=software_role
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "sw_admin", "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.fixture
def enrolled_device(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-SOFTWARE"}, format="json")
    return resp.data["device_id"], resp.data["device_token"]


def _sync_software(device_id, device_token, items):
    return APIClient().post(
        "/api/agent/software/",
        {"items": items},
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )


@pytest.mark.django_db
def test_agent_can_sync_software_list(enrolled_device):
    device_id, device_token = enrolled_device
    response = _sync_software(
        device_id,
        device_token,
        [
            {"name": "Google Chrome", "version": "128.0", "publisher": "Google LLC"},
            {"name": "7-Zip", "version": "23.01", "publisher": "Igor Pavlov", "install_date": "2024-01-15"},
        ],
    )

    assert response.status_code == 201
    assert response.data["synced"] == 2
    assert Software.objects.count() == 2


@pytest.mark.django_db
def test_second_sync_replaces_previous_list(enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(device_id, device_token, [{"name": "Old App", "version": "1.0"}])
    assert Software.objects.count() == 1

    _sync_software(device_id, device_token, [{"name": "New App", "version": "2.0"}])

    assert Software.objects.count() == 1
    assert Software.objects.first().name == "New App"


@pytest.mark.django_db
def test_software_list_requires_permission(enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(device_id, device_token, [{"name": "Chrome", "version": "1.0"}])

    no_perm_role = Role.objects.create(name="NO_SW_PERM")
    viewer = User.objects.create_user(username="noperm2", email="noperm2@example.com", password="StrongPass123!")
    viewer.role = no_perm_role
    viewer.save()
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "noperm2", "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    response = client.get("/api/software/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_software_list_search_and_filter_by_device(admin_client, enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(
        device_id,
        device_token,
        [
            {"name": "Google Chrome", "version": "128.0", "publisher": "Google LLC"},
            {"name": "Mozilla Firefox", "version": "130.0", "publisher": "Mozilla"},
        ],
    )

    all_resp = admin_client.get(f"/api/software/?device={device_id}")
    assert all_resp.data["count"] == 2

    search_resp = admin_client.get("/api/software/?search=chrome")
    assert search_resp.data["count"] == 1
    assert search_resp.data["results"][0]["name"] == "Google Chrome"


@pytest.mark.django_db
def test_software_list_ordering(admin_client, enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(
        device_id,
        device_token,
        [{"name": "Zebra App", "version": "1.0"}, {"name": "Alpha App", "version": "1.0"}],
    )

    response = admin_client.get("/api/software/?ordering=name")
    names = [item["name"] for item in response.data["results"]]
    assert names == ["Alpha App", "Zebra App"]
