import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.alerts.models import Alert
from apps.devices.models import EnrollmentToken
from apps.device_activity.models import AppUsage, BrowsingHistoryEntry, FileActivityEvent
from apps.device_activity.tasks import prune_old_activity
from apps.system_settings.models import SystemSettings


@pytest.fixture
def activity_role(db):
    role = Role.objects.create(name="ACTIVITY_TEST")
    role.permissions.set(
        [
            Permission.objects.create(code="activity.view"),
            Permission.objects.create(code="agent.manage"),
            Permission.objects.create(code="alert.view"),
        ]
    )
    return role


@pytest.fixture
def admin_user(db, activity_role):
    return User.objects.create_user(
        username="activity_admin", email="activity_admin@example.com", password="StrongPass123!", role=activity_role
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    login = client.post(
        "/api/auth/login/", {"username": "activity_admin", "password": "StrongPass123!"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.fixture
def enrolled_device(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    resp = APIClient().post(
        "/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-ACTIVITY"}, format="json"
    )
    return resp.data["device_id"], resp.data["device_token"]


def _agent_post(device_id, device_token, path, payload):
    return APIClient().post(
        path, payload, format="json", HTTP_X_DEVICE_ID=device_id, HTTP_AUTHORIZATION=f"DeviceToken {device_token}"
    )


@pytest.mark.django_db
def test_app_usage_sync_accumulates_duration_across_syncs(enrolled_device, admin_client):
    device_id, device_token = enrolled_device
    payload = {"items": [{"app_name": "chrome.exe", "window_title": "Gmail", "date": "2026-09-17", "duration_seconds": 30}]}

    resp1 = _agent_post(device_id, device_token, "/api/agent/app-usage/", payload)
    assert resp1.status_code == 201
    resp2 = _agent_post(device_id, device_token, "/api/agent/app-usage/", payload)
    assert resp2.status_code == 201

    usage = AppUsage.objects.get(device__device_id=device_id, app_name="chrome.exe")
    assert usage.duration_seconds == 60

    list_resp = admin_client.get(f"/api/app-usage/?device__device_id={device_id}")
    assert list_resp.status_code == 200
    assert list_resp.data["results"][0]["duration_seconds"] == 60


@pytest.mark.django_db
def test_app_usage_requires_activity_permission():
    resp = APIClient().get("/api/app-usage/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_browsing_history_sync_dedupes_identical_entries(enrolled_device, admin_client):
    device_id, device_token = enrolled_device
    payload = {
        "items": [
            {"browser": "Chrome", "url": "https://example.com", "title": "Example", "visited_at": "2026-09-17T10:00:00Z"}
        ]
    }
    _agent_post(device_id, device_token, "/api/agent/browsing-history/", payload)
    _agent_post(device_id, device_token, "/api/agent/browsing-history/", payload)

    assert BrowsingHistoryEntry.objects.filter(device__device_id=device_id).count() == 1

    list_resp = admin_client.get(f"/api/browsing-history/?device__device_id={device_id}")
    assert list_resp.status_code == 200
    assert list_resp.data["count"] == 1


@pytest.mark.django_db
def test_file_activity_sync_creates_events(enrolled_device, admin_client):
    device_id, device_token = enrolled_device
    payload = {
        "items": [
            {"event_type": "CREATED", "path": r"C:\Users\budi\Desktop\report.xlsx", "occurred_at": "2026-09-17T10:00:00Z"}
        ]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/file-activity/", payload)
    assert resp.status_code == 201
    assert FileActivityEvent.objects.filter(device__device_id=device_id).count() == 1

    list_resp = admin_client.get(f"/api/file-activity/?device__device_id={device_id}")
    assert list_resp.status_code == 200
    assert list_resp.data["results"][0]["event_type"] == "CREATED"


@pytest.mark.django_db
def test_usb_event_connected_triggers_alert_and_disconnected_resolves_it(enrolled_device, admin_client):
    device_id, device_token = enrolled_device

    connect_resp = _agent_post(
        device_id, device_token, "/api/agent/usb-event/",
        {"event": "connected", "label": "Kingston 16GB", "drive_letter": "E:", "serial": "ABC123"},
    )
    assert connect_resp.status_code == 201
    alert = Alert.objects.get(device__device_id=device_id, category=Alert.Category.USB)
    assert alert.status == Alert.Status.OPEN
    assert alert.metadata["drive_letter"] == "E:"

    disconnect_resp = _agent_post(
        device_id, device_token, "/api/agent/usb-event/", {"event": "disconnected"}
    )
    assert disconnect_resp.status_code == 201
    alert.refresh_from_db()
    assert alert.status == Alert.Status.RESOLVED


@pytest.mark.django_db
def test_prune_old_activity_deletes_only_past_retention_window(enrolled_device):
    device_id, _ = enrolled_device
    from apps.devices.models import Device

    device = Device.objects.get(device_id=device_id)
    SystemSettings.objects.update_or_create(pk=1, defaults={"activity_retention_days": 30})

    old_cutoff = timezone.now() - datetime.timedelta(days=40)
    recent = timezone.now() - datetime.timedelta(days=1)

    AppUsage.objects.create(device=device, app_name="old.exe", date=old_cutoff.date(), duration_seconds=10)
    AppUsage.objects.create(device=device, app_name="recent.exe", date=recent.date(), duration_seconds=10)
    BrowsingHistoryEntry.objects.create(device=device, browser="Chrome", url="https://old.example", visited_at=old_cutoff)
    BrowsingHistoryEntry.objects.create(device=device, browser="Chrome", url="https://recent.example", visited_at=recent)
    FileActivityEvent.objects.create(device=device, event_type="CREATED", path="old.txt", occurred_at=old_cutoff)
    FileActivityEvent.objects.create(device=device, event_type="CREATED", path="recent.txt", occurred_at=recent)

    deleted = prune_old_activity()

    assert deleted == 3
    assert AppUsage.objects.filter(app_name="old.exe").count() == 0
    assert AppUsage.objects.filter(app_name="recent.exe").count() == 1
    assert BrowsingHistoryEntry.objects.filter(url="https://old.example").count() == 0
    assert BrowsingHistoryEntry.objects.filter(url="https://recent.example").count() == 1
    assert FileActivityEvent.objects.filter(path="old.txt").count() == 0
    assert FileActivityEvent.objects.filter(path="recent.txt").count() == 1
