import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.devices.models import Device, EnrollmentToken
from apps.monitoring.models import DeviceMetric
from apps.monitoring.services import evaluate_status
from config.asgi import application


@pytest.fixture
def monitoring_role(db):
    role = Role.objects.create(name="MONITORING_TEST")
    role.permissions.set(
        [
            Permission.objects.create(code="monitoring.view"),
            Permission.objects.create(code="agent.manage"),
        ]
    )
    return role


@pytest.fixture
def admin_user(db, monitoring_role):
    return User.objects.create_user(
        username="monitor_admin",
        email="monitor_admin@example.com",
        password="StrongPass123!",
        role=monitoring_role,
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    login = client.post(
        "/api/auth/login/", {"username": "monitor_admin", "password": "StrongPass123!"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.fixture
def enrolled_device(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-METRICS"}, format="json"
    )
    return resp.data["device_id"], resp.data["device_token"]


def _post_metric(device_id, device_token, payload):
    return APIClient().post(
        "/api/agent/metrics/",
        payload,
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )


@pytest.mark.django_db
def test_metrics_ingest_creates_record_and_updates_device(enrolled_device):
    device_id, device_token = enrolled_device

    response = _post_metric(
        device_id, device_token, {"cpu_percent": 40, "ram_percent": 50, "disk_percent": 30, "username": "budi"}
    )

    assert response.status_code == 201
    assert response.data["status"] == "ONLINE"

    device = Device.objects.get(device_id=device_id)
    assert device.username == "budi"
    assert device.last_seen is not None
    assert DeviceMetric.objects.filter(device=device).count() == 1


@pytest.mark.django_db
def test_metrics_ingest_sets_warning_and_critical_status(enrolled_device):
    device_id, device_token = enrolled_device

    warning_resp = _post_metric(device_id, device_token, {"cpu_percent": 85})
    assert warning_resp.data["status"] == "WARNING"

    critical_resp = _post_metric(device_id, device_token, {"cpu_percent": 97})
    assert critical_resp.data["status"] == "CRITICAL"

    recovered_resp = _post_metric(device_id, device_token, {"cpu_percent": 5, "ram_percent": 5, "disk_percent": 5})
    assert recovered_resp.data["status"] == "ONLINE"


@pytest.mark.django_db
def test_disabled_device_status_is_not_overridden_by_metrics(monitoring_role, enrolled_device):
    monitoring_role.permissions.add(Permission.objects.create(code="device.disable"))
    device_id, device_token = enrolled_device

    device = Device.objects.get(device_id=device_id)
    device.status = Device.Status.DISABLED
    device.save(update_fields=["status"])

    response = _post_metric(device_id, device_token, {"cpu_percent": 99})

    assert response.status_code == 401  # DeviceTokenAuthentication already blocks disabled devices
    device.refresh_from_db()
    assert device.status == Device.Status.DISABLED


@pytest.mark.django_db
def test_metrics_endpoints_require_monitoring_permission(enrolled_device):
    device_id, device_token = enrolled_device
    _post_metric(device_id, device_token, {"cpu_percent": 10})

    no_perm_role = Role.objects.create(name="NO_PERM_TEST")
    viewer = User.objects.create_user(username="noperm", email="noperm@example.com", password="StrongPass123!")
    viewer.role = no_perm_role
    viewer.save()
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "noperm", "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    response = client.get(f"/api/devices/{device_id}/metrics/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_metrics_latest_and_history(admin_client, enrolled_device):
    device_id, device_token = enrolled_device
    _post_metric(device_id, device_token, {"cpu_percent": 10, "ram_percent": 20})
    _post_metric(device_id, device_token, {"cpu_percent": 15, "ram_percent": 25})

    latest = admin_client.get(f"/api/devices/{device_id}/metrics/")
    assert latest.status_code == 200
    assert latest.data["cpu_percent"] == 15

    history = admin_client.get(f"/api/devices/{device_id}/history/")
    assert history.status_code == 200
    assert history.data["count"] == 2


@pytest.mark.parametrize(
    "cpu,ram,disk,battery,charging,expected",
    [
        (10, 10, 10, None, None, "ONLINE"),
        (85, 10, 10, None, None, "WARNING"),
        (10, 85, 10, None, None, "WARNING"),
        (10, 10, 90, None, None, "WARNING"),
        (97, 10, 10, None, None, "CRITICAL"),
        (10, 10, 10, 5, False, "CRITICAL"),
        (10, 10, 10, 5, True, "ONLINE"),  # low battery but charging is not critical
    ],
)
def test_evaluate_status_thresholds(cpu, ram, disk, battery, charging, expected):
    result = evaluate_status(
        cpu_percent=cpu, ram_percent=ram, disk_percent=disk, battery_percent=battery, battery_charging=charging
    )
    assert result == expected


@pytest.mark.django_db
def test_dashboard_ws_rejects_missing_token():
    async def run():
        communicator = WebsocketCommunicator(application, "/ws/dashboard/")
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_dashboard_ws_receives_metric_broadcast(admin_user, enrolled_device):
    device_id, device_token = enrolled_device

    from rest_framework_simplejwt.tokens import RefreshToken

    access = str(RefreshToken.for_user(admin_user).access_token)

    async def run():
        communicator = WebsocketCommunicator(application, f"/ws/dashboard/?token={access}")
        connected, _ = await communicator.connect()
        assert connected is True

        from channels.db import database_sync_to_async

        await database_sync_to_async(_post_metric)(device_id, device_token, {"cpu_percent": 33})

        message = await communicator.receive_json_from(timeout=5)
        assert message["type"] == "device.metric"
        assert message["payload"]["device_id"] == device_id
        assert message["payload"]["cpu_percent"] == 33

        await communicator.disconnect()

    async_to_sync(run)()
