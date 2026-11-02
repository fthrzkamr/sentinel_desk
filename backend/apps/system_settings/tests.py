import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.audit.models import AuditLog
from apps.monitoring.services import evaluate_status

from .models import SystemSettings


@pytest.fixture
def manager_role(db):
    role = Role.objects.create(name="SETTINGS_MANAGER")
    role.permissions.set([Permission.objects.create(code="settings.manage")])
    return role


@pytest.fixture
def no_perm_role(db):
    return Role.objects.create(name="NO_SETTINGS_PERM")


@pytest.fixture
def manager_user(db, manager_role):
    return User.objects.create_user(
        username="settings_admin", email="settings_admin@example.com", password="StrongPass123!", role=manager_role
    )


@pytest.fixture
def no_perm_user(db, no_perm_role):
    return User.objects.create_user(
        username="settings_noperm", email="settings_noperm@example.com", password="StrongPass123!", role=no_perm_role
    )


def _client_for(username):
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.mark.django_db
def test_get_solo_creates_row_seeded_from_env_defaults():
    config = SystemSettings.get_solo()
    assert config.pk == 1
    assert config.cpu_warning_percent == 80
    assert config.cpu_critical_percent == 95

    # a second call must return the same row, not create another
    again = SystemSettings.get_solo()
    assert again.pk == config.pk
    assert SystemSettings.objects.count() == 1


@pytest.mark.django_db
def test_settings_view_requires_permission(manager_user, no_perm_user):
    denied = _client_for("settings_noperm").get("/api/settings/")
    assert denied.status_code == 403

    allowed = _client_for("settings_admin").get("/api/settings/")
    assert allowed.status_code == 200
    assert allowed.data["cpu_warning_percent"] == 80


@pytest.mark.django_db
def test_manager_can_update_thresholds_and_it_takes_effect_immediately(manager_user):
    client = _client_for("settings_admin")
    response = client.patch("/api/settings/", {"cpu_warning_percent": 50, "cpu_critical_percent": 60}, format="json")
    assert response.status_code == 200
    assert response.data["cpu_warning_percent"] == 50
    assert response.data["cpu_critical_percent"] == 60

    assert AuditLog.objects.filter(action="settings.updated", user=manager_user).exists()

    # no restart needed — evaluate_status reads the DB-backed solo config
    status = evaluate_status(
        cpu_percent=55, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None
    )
    assert status == "WARNING"


@pytest.mark.django_db
def test_warning_threshold_must_be_below_critical(manager_user):
    client = _client_for("settings_admin")
    response = client.patch(
        "/api/settings/", {"cpu_warning_percent": 96, "cpu_critical_percent": 95}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_offline_threshold_has_a_sane_minimum(manager_user):
    client = _client_for("settings_admin")
    response = client.patch("/api/settings/", {"device_offline_threshold_seconds": 2}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_percent_fields_are_bounded_0_to_100(manager_user):
    client = _client_for("settings_admin")
    response = client.patch("/api/settings/", {"ram_warning_percent": 150}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_data_exfil_min_local_files_survives_cache_roundtrip(manager_user):
    client = _client_for("settings_admin")
    response = client.patch("/api/settings/", {"data_exfil_min_local_files": 5}, format="json")
    assert response.status_code == 200
    assert response.data["data_exfil_min_local_files"] == 5

    # First call populates the Redis cache; second call reads from the cached dict
    first = SystemSettings.get_solo()
    second = SystemSettings.get_solo()
    assert first.data_exfil_min_local_files == 5
    assert second.data_exfil_min_local_files == 5


@pytest.mark.django_db
def test_telegram_fields_must_be_paired(manager_user):
    client = _client_for("settings_admin")
    resp = client.patch("/api/settings/", {"telegram_bot_token": "123:ABC", "telegram_chat_id": ""}, format="json")
    assert resp.status_code == 400
    assert "telegram_chat_id" in resp.data

    ok = client.patch(
        "/api/settings/", {"telegram_bot_token": "123:ABC", "telegram_chat_id": "-100999"}, format="json"
    )
    assert ok.status_code == 200


@pytest.mark.django_db
def test_notification_emails_validates_format(manager_user):
    client = _client_for("settings_admin")
    bad = client.patch("/api/settings/", {"notification_emails": "valid@example.com, not-an-email"}, format="json")
    assert bad.status_code == 400
    assert "notification_emails" in bad.data

    good = client.patch(
        "/api/settings/", {"notification_emails": "sec@example.com, admin@example.com"}, format="json"
    )
    assert good.status_code == 200
    assert good.data["notification_emails"] == "sec@example.com, admin@example.com"


@pytest.mark.django_db
def test_test_notification_endpoint_requires_channel_and_dispatches(manager_user, mailoutbox, monkeypatch):
    client = _client_for("settings_admin")

    # No channel configured -> 400
    empty_resp = client.post("/api/settings/test-notification/", {}, format="json")
    assert empty_resp.status_code == 400

    posted_webhooks = []

    def fake_post_json(url, payload, timeout=10):
        posted_webhooks.append((url, payload))

    monkeypatch.setattr("apps.alerts.notifications._post_json", fake_post_json)

    resp = client.post(
        "/api/settings/test-notification/",
        {
            "telegram_bot_token": "123:TOKEN",
            "telegram_chat_id": "-100123",
            "webhook_url": "https://hooks.example.com/alert",
            "notification_emails": "soc@example.com",
        },
        format="json",
    )
    assert resp.status_code == 200
    assert set(resp.data["sent"]) == {"telegram", "webhook", "email"}
    assert resp.data["errors"] == {}
    assert len(posted_webhooks) == 2
    assert len(mailoutbox) == 1
    assert "Test Notification" in mailoutbox[0].subject
    assert AuditLog.objects.filter(action="settings.test_notification_sent", user=manager_user).exists()


@pytest.mark.django_db
def test_agent_policy_fields_and_binary_upload_ota(manager_user, tmp_path, settings, monkeypatch):
    import hashlib
    from io import BytesIO
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = tmp_path
    client = _client_for("settings_admin")

    # 1. Update remote policy via PATCH
    patch_resp = client.patch(
        "/api/settings/",
        {
            "agent_metrics_interval_seconds": 25,
            "agent_screen_monitor_enabled": False,
            "agent_usb_monitor_enabled": True,
        },
        format="json",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.data["agent_metrics_interval_seconds"] == 25
    assert patch_resp.data["agent_screen_monitor_enabled"] is False

    solo = SystemSettings.get_solo()
    assert solo.agent_metrics_interval_seconds == 25
    assert solo.agent_screen_monitor_enabled is False

    # 2. Upload binary agent
    dummy_exe_content = b"MZSentinelDeskDummyBinaryContent12345"
    expected_hash = hashlib.sha256(dummy_exe_content).hexdigest()
    uploaded = SimpleUploadedFile("agent.exe", dummy_exe_content, content_type="application/octet-stream")

    upload_resp = client.post(
        "/api/settings/agent-binary/",
        {"version": "0.8.16", "file": uploaded},
        format="multipart",
    )
    assert upload_resp.status_code == 201
    assert upload_resp.data["version"] == "0.8.16"
    assert upload_resp.data["sha256"] == expected_hash
    assert upload_resp.data["download_url"] == "/api/agent/download/0.8.16/"
    assert upload_resp.data["auto_update_enabled"] is True

    saved_file = tmp_path / "agent" / "SentinelDeskAgent-0.8.16.exe"
    assert saved_file.exists()
    assert saved_file.read_bytes() == dummy_exe_content

    solo.refresh_from_db()
    solo = SystemSettings.get_solo()
    assert solo.agent_latest_version == "0.8.16"
    assert solo.agent_sha256 == expected_hash
    assert solo.agent_auto_update_enabled is True
    assert AuditLog.objects.filter(action="agent.release_uploaded", user=manager_user).exists()

