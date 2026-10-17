import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.alerts.models import Alert
from apps.devices.models import EnrollmentToken
from apps.software.models import Software, SoftwareWhitelistEntry


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
def test_first_sync_does_not_trigger_new_software_alert(enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(
        device_id,
        device_token,
        [{"name": "Google Chrome", "version": "128.0"}, {"name": "7-Zip", "version": "23.01"}],
    )

    assert Alert.objects.filter(category=Alert.Category.NEW_SOFTWARE).count() == 0


@pytest.mark.django_db
def test_second_sync_with_new_app_triggers_alert(enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(device_id, device_token, [{"name": "Google Chrome", "version": "128.0"}])

    _sync_software(
        device_id, device_token, [{"name": "Google Chrome", "version": "128.0"}, {"name": "Discord", "version": "1.0"}]
    )

    alert = Alert.objects.get(category=Alert.Category.NEW_SOFTWARE)
    assert alert.status == Alert.Status.OPEN
    assert alert.severity == Alert.Severity.WARNING
    assert "Discord" in alert.message
    assert alert.metadata["names"] == ["Discord"]


@pytest.mark.django_db
def test_second_sync_with_no_new_app_does_not_trigger_alert(enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(device_id, device_token, [{"name": "Google Chrome", "version": "128.0"}])
    _sync_software(device_id, device_token, [{"name": "Google Chrome", "version": "129.0"}])

    assert Alert.objects.filter(category=Alert.Category.NEW_SOFTWARE).count() == 0


@pytest.mark.django_db
def test_unwhitelisted_software_triggers_critical_alert(enrolled_device):
    device_id, device_token = enrolled_device
    SoftwareWhitelistEntry.objects.create(name="Google Chrome")
    _sync_software(device_id, device_token, [{"name": "Google Chrome", "version": "128.0"}])

    _sync_software(
        device_id,
        device_token,
        [
            {"name": "Google Chrome", "version": "128.0"},
            {"name": "BitTorrent", "version": "1.0"},
        ],
    )

    alert = Alert.objects.get(category=Alert.Category.NEW_SOFTWARE)
    assert alert.severity == Alert.Severity.CRITICAL
    assert "TIDAK di whitelist" in alert.message
    assert "BitTorrent" in alert.message
    assert alert.metadata["unauthorized"] is True


@pytest.mark.django_db
def test_whitelisted_software_does_not_trigger_alert(enrolled_device):
    device_id, device_token = enrolled_device
    SoftwareWhitelistEntry.objects.create(name="Google Chrome")
    SoftwareWhitelistEntry.objects.create(name="Zoom")
    _sync_software(device_id, device_token, [{"name": "Google Chrome", "version": "128.0"}])

    _sync_software(
        device_id,
        device_token,
        [{"name": "Google Chrome", "version": "128.0"}, {"name": "Zoom", "version": "5.0"}],
    )

    assert Alert.objects.filter(category=Alert.Category.NEW_SOFTWARE).count() == 0


@pytest.mark.django_db
def test_empty_whitelist_keeps_default_warning_alert(enrolled_device):
    device_id, device_token = enrolled_device
    _sync_software(device_id, device_token, [{"name": "Google Chrome", "version": "128.0"}])

    _sync_software(
        device_id,
        device_token,
        [{"name": "Google Chrome", "version": "128.0"}, {"name": "Discord", "version": "1.0"}],
    )

    alert = Alert.objects.get(category=Alert.Category.NEW_SOFTWARE)
    assert alert.severity == Alert.Severity.WARNING
    assert alert.metadata["unauthorized"] is False


@pytest.mark.django_db
def test_whitelist_crud_requires_manage_permission(enrolled_device, admin_client):
    resp = admin_client.post("/api/software-whitelist/", {"name": "Google Chrome"}, format="json")
    assert resp.status_code == 403

    manage_role = Role.objects.create(name="SOFTWARE_MANAGE_TEST")
    manage_role.permissions.set([Permission.objects.create(code="software.manage")])
    manage_user = User.objects.create_user(
        username="sw_manager", email="sw_manager@example.com", password="StrongPass123!", role=manage_role
    )
    manage_client = APIClient()
    login = manage_client.post(
        "/api/auth/login/", {"username": "sw_manager", "password": "StrongPass123!"}, format="json"
    )
    manage_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    create_resp = manage_client.post("/api/software-whitelist/", {"name": "Google Chrome"}, format="json")
    assert create_resp.status_code == 201
    entry_id = create_resp.data["id"]
    assert create_resp.data["added_by"] == "sw_manager"

    list_resp = manage_client.get("/api/software-whitelist/")
    assert list_resp.status_code == 200
    assert len(list_resp.data) == 1

    delete_resp = manage_client.delete(f"/api/software-whitelist/{entry_id}/")
    assert delete_resp.status_code == 204
    assert SoftwareWhitelistEntry.objects.count() == 0


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
