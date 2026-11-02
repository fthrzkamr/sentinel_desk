import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.alerts.models import Alert
from apps.devices.models import EnrollmentToken
from apps.device_activity.models import AppUsage, BrowsingHistoryEntry, FileActivityEvent, IdleActivityStat
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
def test_browsing_history_filters_by_date_range(enrolled_device, admin_client):
    device_id, device_token = enrolled_device
    _agent_post(
        device_id,
        device_token,
        "/api/agent/browsing-history/",
        {"items": [{"browser": "Chrome", "url": "https://old.example.com", "title": "Old", "visited_at": "2026-09-10T10:00:00Z"}]},
    )
    _agent_post(
        device_id,
        device_token,
        "/api/agent/browsing-history/",
        {"items": [{"browser": "Chrome", "url": "https://new.example.com", "title": "New", "visited_at": "2026-09-20T10:00:00Z"}]},
    )

    resp = admin_client.get(
        f"/api/browsing-history/?device__device_id={device_id}&visited_at__gte=2026-09-15T00:00:00Z"
    )
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["url"] == "https://new.example.com"


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
def test_idle_activity_sync_creates_stat(enrolled_device, admin_client):
    device_id, device_token = enrolled_device
    payload = {"items": [{"date": "2026-09-17", "active_seconds": 120, "idle_seconds": 30}]}

    resp = _agent_post(device_id, device_token, "/api/agent/idle-activity/", payload)
    assert resp.status_code == 201

    stat = IdleActivityStat.objects.get(device__device_id=device_id, date="2026-09-17")
    assert stat.active_seconds == 120
    assert stat.idle_seconds == 30
    assert stat.active_percent == 80.0

    list_resp = admin_client.get(f"/api/idle-activity/?device__device_id={device_id}")
    assert list_resp.status_code == 200
    assert list_resp.data["results"][0]["active_percent"] == 80.0


@pytest.mark.django_db
def test_idle_activity_sync_accumulates_across_syncs(enrolled_device):
    device_id, device_token = enrolled_device
    payload = {"items": [{"date": "2026-09-17", "active_seconds": 100, "idle_seconds": 20}]}

    _agent_post(device_id, device_token, "/api/agent/idle-activity/", payload)
    _agent_post(device_id, device_token, "/api/agent/idle-activity/", payload)

    stat = IdleActivityStat.objects.get(device__device_id=device_id, date="2026-09-17")
    assert stat.active_seconds == 200
    assert stat.idle_seconds == 40


@pytest.mark.django_db
def test_idle_activity_percent_is_none_with_no_data(enrolled_device):
    device_id, _ = enrolled_device
    from apps.devices.models import Device

    device = Device.objects.get(device_id=device_id)
    stat = IdleActivityStat.objects.create(device=device, date="2026-09-17")
    assert stat.active_percent is None


@pytest.mark.django_db
def test_file_activity_filters_by_date_range(enrolled_device, admin_client):
    device_id, device_token = enrolled_device
    _agent_post(
        device_id,
        device_token,
        "/api/agent/file-activity/",
        {"items": [{"event_type": "CREATED", "path": r"C:\old.txt", "occurred_at": "2026-09-10T10:00:00Z"}]},
    )
    _agent_post(
        device_id,
        device_token,
        "/api/agent/file-activity/",
        {"items": [{"event_type": "CREATED", "path": r"C:\new.txt", "occurred_at": "2026-09-20T10:00:00Z"}]},
    )

    resp = admin_client.get(
        f"/api/file-activity/?device__device_id={device_id}&occurred_at__lte=2026-09-15T00:00:00Z"
    )
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["path"] == r"C:\old.txt"


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
    IdleActivityStat.objects.create(device=device, date=old_cutoff.date(), active_seconds=10)
    IdleActivityStat.objects.create(device=device, date=recent.date(), active_seconds=10)

    deleted = prune_old_activity()

    assert deleted == 4
    assert AppUsage.objects.filter(app_name="old.exe").count() == 0
    assert AppUsage.objects.filter(app_name="recent.exe").count() == 1
    assert BrowsingHistoryEntry.objects.filter(url="https://old.example").count() == 0
    assert BrowsingHistoryEntry.objects.filter(url="https://recent.example").count() == 1
    assert FileActivityEvent.objects.filter(path="old.txt").count() == 0
    assert FileActivityEvent.objects.filter(path="recent.txt").count() == 1
    assert IdleActivityStat.objects.filter(date=old_cutoff.date()).count() == 0
    assert IdleActivityStat.objects.filter(date=recent.date()).count() == 1


# --- Out-of-hours and data-exfiltration alerts ---


def _local(hour):
    naive = datetime.datetime(2026, 1, 15, hour, 0)
    return timezone.make_aware(naive, timezone.get_current_timezone())


@pytest.mark.django_db
def test_browsing_outside_work_hours_triggers_alert(enrolled_device):
    device_id, device_token = enrolled_device
    SystemSettings.objects.update_or_create(pk=1, defaults={"work_hours_start": 8, "work_hours_end": 18})

    payload = {
        "items": [{"browser": "Chrome", "url": "https://example.com", "title": "x", "visited_at": _local(2).isoformat()}]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/browsing-history/", payload)
    assert resp.status_code == 201

    assert Alert.objects.filter(device__device_id=device_id, category=Alert.Category.OUT_OF_HOURS).exists()


@pytest.mark.django_db
def test_browsing_within_work_hours_does_not_trigger_alert(enrolled_device):
    device_id, device_token = enrolled_device
    SystemSettings.objects.update_or_create(pk=1, defaults={"work_hours_start": 8, "work_hours_end": 18})

    payload = {
        "items": [{"browser": "Chrome", "url": "https://example.com", "title": "x", "visited_at": _local(10).isoformat()}]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/browsing-history/", payload)
    assert resp.status_code == 201

    assert not Alert.objects.filter(device__device_id=device_id, category=Alert.Category.OUT_OF_HOURS).exists()


@pytest.mark.django_db
def test_usb_sourced_file_creation_triggers_data_exfil_alert(enrolled_device):
    device_id, device_token = enrolled_device
    payload = {
        "items": [
            {
                "event_type": "CREATED",
                "path": r"E:\confidential_report.xlsx",
                "source": "USB",
                "occurred_at": _local(10).isoformat(),
            }
        ]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/file-activity/", payload)
    assert resp.status_code == 201

    alert = Alert.objects.get(device__device_id=device_id, category=Alert.Category.DATA_EXFIL)
    assert alert.severity == Alert.Severity.CRITICAL
    assert alert.metadata["drive_letter"] == "E:"


@pytest.mark.django_db
def test_local_sourced_file_creation_does_not_trigger_data_exfil_alert(enrolled_device):
    device_id, device_token = enrolled_device
    payload = {
        "items": [
            {
                "event_type": "CREATED",
                "path": r"C:\Users\budi\Desktop\report.xlsx",
                "occurred_at": _local(10).isoformat(),
            }
        ]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/file-activity/", payload)
    assert resp.status_code == 201

    assert not Alert.objects.filter(device__device_id=device_id, category=Alert.Category.DATA_EXFIL).exists()


@pytest.mark.django_db
def test_visiting_file_sharing_site_alone_does_not_trigger_data_exfil_alert(enrolled_device):
    """A file-sharing-site visit with no recent local file activity behind
    it is ordinary daily use (browsing an existing shared folder, reading
    something someone else uploaded) - not a signal worth alerting on by
    itself. See trigger_cloud_upload_alert's docstring."""
    device_id, device_token = enrolled_device
    payload = {
        "items": [
            {"browser": "Edge", "url": "https://drive.google.com/drive/u/0/my-drive", "title": "My Drive", "visited_at": _local(10).isoformat()}
        ]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/browsing-history/", payload)
    assert resp.status_code == 201

    assert not Alert.objects.filter(device__device_id=device_id, category=Alert.Category.DATA_EXFIL).exists()


@pytest.mark.django_db
def test_file_sharing_visit_below_min_local_files_threshold_does_not_trigger_alert(enrolled_device):
    device_id, device_token = enrolled_device

    file_payload = {
        "items": [
            {
                "event_type": "CREATED",
                "path": r"C:\Users\budi\Documents\single_doc.xlsx",
                "occurred_at": _local(10).isoformat(),
            }
        ]
    }
    assert _agent_post(device_id, device_token, "/api/agent/file-activity/", file_payload).status_code == 201

    naive = datetime.datetime(2026, 1, 15, 10, 5)
    visited_at = timezone.make_aware(naive, timezone.get_current_timezone())
    browse_payload = {
        "items": [{"browser": "Edge", "url": "https://wetransfer.com/", "title": "WeTransfer", "visited_at": visited_at.isoformat()}]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/browsing-history/", browse_payload)
    assert resp.status_code == 201

    assert not Alert.objects.filter(device__device_id=device_id, category=Alert.Category.DATA_EXFIL).exists()


@pytest.mark.django_db
def test_file_sharing_visit_with_recent_local_file_activity_escalates_to_critical(enrolled_device):
    device_id, device_token = enrolled_device

    file_payload = {
        "items": [
            {
                "event_type": "CREATED",
                "path": r"C:\Users\budi\Documents\client_list.xlsx",
                "occurred_at": _local(10).isoformat(),
            },
            {
                "event_type": "MODIFIED",
                "path": r"C:\Users\budi\Documents\pricing_2026.xlsx",
                "occurred_at": _local(10).isoformat(),
            },
        ]
    }
    assert _agent_post(device_id, device_token, "/api/agent/file-activity/", file_payload).status_code == 201

    naive = datetime.datetime(2026, 1, 15, 10, 5)
    visited_at = timezone.make_aware(naive, timezone.get_current_timezone())
    browse_payload = {
        "items": [{"browser": "Edge", "url": "https://wetransfer.com/", "title": "WeTransfer", "visited_at": visited_at.isoformat()}]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/browsing-history/", browse_payload)
    assert resp.status_code == 201

    alert = Alert.objects.get(device__device_id=device_id, category=Alert.Category.DATA_EXFIL)
    assert alert.severity == Alert.Severity.CRITICAL
    assert alert.metadata["recent_local_file_count"] == 2


@pytest.mark.django_db
def test_visiting_non_file_sharing_site_does_not_trigger_exfil_alert(enrolled_device):
    device_id, device_token = enrolled_device
    payload = {
        "items": [{"browser": "Edge", "url": "https://www.wikipedia.org/", "title": "Wikipedia", "visited_at": _local(10).isoformat()}]
    }
    resp = _agent_post(device_id, device_token, "/api/agent/browsing-history/", payload)
    assert resp.status_code == 201

    assert not Alert.objects.filter(device__device_id=device_id, category=Alert.Category.DATA_EXFIL).exists()


@pytest.mark.django_db
def test_cloud_upload_alert_shares_category_with_usb_exfil_alert(enrolled_device):
    """Both vectors write to the same DATA_EXFIL category, so firing one
    after the other reuses the existing open alert instead of creating a
    second row — same dedup behavior _trigger() already guarantees."""
    device_id, device_token = enrolled_device

    usb_payload = {
        "items": [
            {
                "event_type": "CREATED",
                "path": r"E:\report.xlsx",
                "source": "USB",
                "occurred_at": _local(10).isoformat(),
            }
        ]
    }
    assert _agent_post(device_id, device_token, "/api/agent/file-activity/", usb_payload).status_code == 201

    browse_payload = {
        "items": [{"browser": "Edge", "url": "https://drive.google.com/", "title": "Drive", "visited_at": _local(11).isoformat()}]
    }
    assert _agent_post(device_id, device_token, "/api/agent/browsing-history/", browse_payload).status_code == 201

    assert Alert.objects.filter(device__device_id=device_id, category=Alert.Category.DATA_EXFIL).count() == 1


@pytest.mark.django_db
def test_usb_and_activity_alerts_broadcast_to_dashboard_ws(enrolled_device, monkeypatch):
    device_id, device_token = enrolled_device
    events = []

    def fake_broadcast(event_type, payload):
        events.append((event_type, payload))

    monkeypatch.setattr("apps.monitoring.broadcast.broadcast_dashboard_event", fake_broadcast)

    connect_resp = _agent_post(
        device_id,
        device_token,
        "/api/agent/usb-event/",
        {"event": "connected", "label": "SanDisk", "drive_letter": "F:", "serial": "SN999"},
    )
    assert connect_resp.status_code == 201
    assert len(events) == 1
    assert events[0][0] == "alert.triggered"
    assert events[0][1]["category"] == Alert.Category.USB

    disconnect_resp = _agent_post(
        device_id,
        device_token,
        "/api/agent/usb-event/",
        {"event": "disconnected", "drive_letter": "F:"},
    )
    assert disconnect_resp.status_code == 201
    assert len(events) == 2
    assert events[1][0] == "alert.updated"
    assert events[1][1]["status"] == Alert.Status.RESOLVED
