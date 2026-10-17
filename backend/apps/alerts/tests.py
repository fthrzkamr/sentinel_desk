import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.alerts.models import Alert
from apps.alerts.services import (
    compute_risk_score,
    sync_metric_alerts,
    trigger_connectivity_alert,
    trigger_suspicious_url_alert,
    trigger_usb_alert,
)
from apps.alerts.url_analysis import classify_url
from apps.audit.models import AuditLog
from apps.devices.models import Device, EnrollmentToken


@pytest.fixture
def manager_role(db):
    role = Role.objects.create(name="ALERT_MANAGER")
    role.permissions.set(
        [
            Permission.objects.get_or_create(code="alert.view")[0],
            Permission.objects.get_or_create(code="alert.manage")[0],
            Permission.objects.get_or_create(code="agent.manage")[0],
        ]
    )
    return role


@pytest.fixture
def viewer_role(db):
    role = Role.objects.create(name="ALERT_VIEWER_ONLY")
    role.permissions.set([Permission.objects.get_or_create(code="alert.view")[0]])
    return role


@pytest.fixture
def manager_user(db, manager_role):
    return User.objects.create_user(
        username="alert_admin", email="alert_admin@example.com", password="StrongPass123!", role=manager_role
    )


@pytest.fixture
def viewer_user(db, viewer_role):
    return User.objects.create_user(
        username="alert_viewer", email="alert_viewer@example.com", password="StrongPass123!", role=viewer_role
    )


def _client_for(username, password="StrongPass123!"):
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": password}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.fixture
def manager_client(manager_user):
    return _client_for("alert_admin")


@pytest.fixture
def viewer_client(viewer_user):
    return _client_for("alert_viewer")


@pytest.fixture
def enrolled(manager_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=manager_user, ttl_minutes=60)
    resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-ALERTS"}, format="json")
    return Device.objects.get(device_id=resp.data["device_id"]), resp.data["device_token"]


@pytest.fixture
def device(enrolled):
    return enrolled[0]


@pytest.mark.django_db
def test_high_cpu_creates_open_alert(device):
    triggered, resolved = sync_metric_alerts(
        device, cpu_percent=97, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None
    )
    assert len(triggered) == 1
    assert resolved == []
    alert = Alert.objects.get(device=device, category=Alert.Category.CPU)
    assert alert.status == Alert.Status.OPEN
    assert alert.severity == Alert.Severity.CRITICAL


@pytest.mark.django_db
def test_repeated_high_cpu_does_not_duplicate_open_alert(device):
    sync_metric_alerts(device, cpu_percent=97, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None)
    triggered_again, _ = sync_metric_alerts(
        device, cpu_percent=98, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None
    )
    assert triggered_again == []
    assert Alert.objects.filter(device=device, category=Alert.Category.CPU).count() == 1


@pytest.mark.django_db
def test_cpu_back_to_normal_auto_resolves_alert(device):
    sync_metric_alerts(device, cpu_percent=97, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None)
    _, resolved = sync_metric_alerts(
        device, cpu_percent=20, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None
    )
    assert len(resolved) == 1
    alert = Alert.objects.get(device=device, category=Alert.Category.CPU)
    assert alert.status == Alert.Status.RESOLVED
    assert alert.metadata["resolution"] == "back_to_normal"


@pytest.mark.django_db
def test_battery_alert_only_when_discharging(device):
    triggered, _ = sync_metric_alerts(
        device, cpu_percent=10, ram_percent=10, disk_percent=10, battery_percent=5, battery_charging=True
    )
    assert triggered == []
    triggered, _ = sync_metric_alerts(
        device, cpu_percent=10, ram_percent=10, disk_percent=10, battery_percent=5, battery_charging=False
    )
    assert len(triggered) == 1
    assert triggered[0].category == Alert.Category.BATTERY


@pytest.mark.django_db
def test_alert_list_requires_permission(device, viewer_client):
    sync_metric_alerts(device, cpu_percent=97, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None)
    response = viewer_client.get("/api/alerts/")
    assert response.status_code == 200
    assert response.data["count"] == 1

    anonymous = APIClient()
    assert anonymous.get("/api/alerts/").status_code == 401


@pytest.mark.django_db
def test_viewer_cannot_acknowledge_alert(device, viewer_client):
    sync_metric_alerts(device, cpu_percent=97, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None)
    alert = Alert.objects.get(device=device)
    response = viewer_client.post(f"/api/alerts/{alert.id}/acknowledge/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_can_acknowledge_then_resolve_alert(device, manager_client, manager_user):
    sync_metric_alerts(device, cpu_percent=97, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None)
    alert = Alert.objects.get(device=device)

    ack_response = manager_client.post(f"/api/alerts/{alert.id}/acknowledge/")
    assert ack_response.status_code == 200
    assert ack_response.data["status"] == "ACKNOWLEDGED"
    assert AuditLog.objects.filter(action="alert.acknowledged", user=manager_user).exists()

    resolve_response = manager_client.post(f"/api/alerts/{alert.id}/resolve/")
    assert resolve_response.status_code == 200
    assert resolve_response.data["status"] == "RESOLVED"
    assert AuditLog.objects.filter(action="alert.resolved", user=manager_user).exists()

    # already resolved -> second resolve call is rejected, not silently re-logged
    second_resolve = manager_client.post(f"/api/alerts/{alert.id}/resolve/")
    assert second_resolve.status_code == 400


@pytest.mark.django_db
def test_alert_summary_counts(device, manager_client):
    sync_metric_alerts(device, cpu_percent=97, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None)
    response = manager_client.get("/api/alerts/summary/")
    assert response.status_code == 200
    assert response.data["open"] == 1
    assert response.data["open_critical"] == 1
    assert response.data["unacknowledged"] == 1


@pytest.mark.django_db
def test_connectivity_alert_trigger_and_resolve_helpers(device):
    alert = trigger_connectivity_alert(device)
    assert alert.category == Alert.Category.CONNECTIVITY
    assert alert.status == Alert.Status.OPEN

    again = trigger_connectivity_alert(device)
    assert again is None  # already open, not duplicated

    triggered, resolved = sync_metric_alerts(
        device, cpu_percent=10, ram_percent=10, disk_percent=10, battery_percent=None, battery_charging=None
    )
    # metric sync alone doesn't touch connectivity alerts — that's the view's job
    assert Alert.objects.get(pk=alert.pk).status == Alert.Status.OPEN


@pytest.mark.django_db
def test_device_coming_back_online_resolves_connectivity_alert(enrolled):
    device, device_token = enrolled
    alert = trigger_connectivity_alert(device)
    device.status = Device.Status.OFFLINE
    device.save(update_fields=["status"])

    response = APIClient().post(
        "/api/agent/metrics/",
        {"cpu_percent": 10, "ram_percent": 10, "disk_percent": 10},
        format="json",
        HTTP_X_DEVICE_ID=device.device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )
    assert response.status_code == 201
    assert Alert.objects.get(pk=alert.pk).status == Alert.Status.RESOLVED


@pytest.mark.django_db
def test_risk_score_is_zero_with_no_alerts(device):
    result = compute_risk_score(device)
    assert result == {"score": 0, "level": "LOW", "window_days": 30, "breakdown": []}


@pytest.mark.django_db
def test_risk_score_weighs_unresolved_alerts_higher(device):
    alert = trigger_usb_alert(device, label="SanDisk", drive_letter="F:", serial="abc123")

    open_result = compute_risk_score(device)
    assert open_result["score"] == 15  # 10 * 1.5 (still open)
    assert open_result["breakdown"] == [{"category": "USB", "count": 1, "unresolved_count": 1, "points": 15.0}]

    alert.status = Alert.Status.RESOLVED
    alert.save(update_fields=["status"])

    resolved_result = compute_risk_score(device)
    assert resolved_result["score"] == 10  # full weight once resolved, no more multiplier
    assert resolved_result["breakdown"][0]["unresolved_count"] == 0


@pytest.mark.django_db
def test_risk_score_ignores_alerts_outside_the_window(device):
    from django.utils import timezone

    alert = trigger_usb_alert(device, label="SanDisk", drive_letter="F:", serial="abc123")
    alert.triggered_at = timezone.now() - timezone.timedelta(days=45)
    Alert.objects.filter(pk=alert.pk).update(triggered_at=alert.triggered_at)

    result = compute_risk_score(device, window_days=30)
    assert result["score"] == 0


@pytest.mark.django_db
def test_risk_score_caps_at_100(device):
    for _ in range(10):
        # Resolve the previous one first so _trigger's open-alert lookup
        # can't find and reuse it — each loop iteration must land a
        # genuinely new row for the count to actually accumulate.
        alert = trigger_usb_alert(device, label="SanDisk", drive_letter="F:", serial="abc123")
        alert.status = Alert.Status.RESOLVED
        alert.save(update_fields=["status"])

    result = compute_risk_score(device)
    assert Alert.objects.filter(device=device, category=Alert.Category.USB).count() == 10
    assert result["score"] == 100  # 10 * 10 points = 100, capped
    assert result["level"] == "HIGH"


@pytest.mark.django_db
def test_risk_score_endpoint_requires_permission(device, viewer_client):
    response = viewer_client.get(f"/api/devices/{device.device_id}/risk-score/")
    assert response.status_code == 200  # viewer_role has alert.view

    no_perm_role = Role.objects.create(name="NO_ALERT_PERM")
    no_perm_user = User.objects.create_user(
        username="no_perm_risk", email="no_perm_risk@example.com", password="StrongPass123!", role=no_perm_role
    )
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "no_perm_risk", "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    response = client.get(f"/api/devices/{device.device_id}/risk-score/")
    assert response.status_code == 403


# --- classify_url() heuristics ---


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com/search?q=test",
        "https://docs.python.org/3/library/urllib.parse.html",
        "https://mail.google.com/mail/u/0/",
        "https://www.bca.co.id/login",
    ],
)
def test_classify_url_does_not_flag_legitimate_urls(url):
    assert classify_url(url) == []


def test_classify_url_flags_raw_ip_host():
    assert "host adalah alamat IP mentah" in classify_url("http://192.168.1.50/login")


def test_classify_url_flags_punycode_domain():
    assert "domain punycode/homograph" in classify_url("https://xn--pypal-4ve.com/verify")


def test_classify_url_flags_excessive_subdomains():
    assert "subdomain berlapis berlebihan" in classify_url("https://a.b.c.d.example.com/")


def test_classify_url_flags_brand_typosquat():
    reasons = classify_url("https://paypal.security-check-login.ru/verify")
    assert any("meniru domain 'paypal'" in r for r in reasons)


def test_classify_url_flags_suspicious_keyword_on_unknown_domain():
    reasons = classify_url("http://update-account.totally-not-a-bank.xyz/")
    assert any("kata kunci mencurigakan" in r for r in reasons)


def test_classify_url_stacks_multiple_reasons():
    # Excessive subdomain depth (5 labels) + a suspicious keyword ("verify")
    # sitting right in the hostname itself, on a domain with no brand match.
    reasons = classify_url("http://secure.verify.account.suspicious-domain.xyz/")
    assert len(reasons) >= 2


# --- trigger_suspicious_url_alert() ---


@pytest.mark.django_db
def test_suspicious_url_single_reason_is_warning(device):
    alert = trigger_suspicious_url_alert(
        device, url="http://192.168.1.50/login", title="Login", reasons=["host adalah alamat IP mentah"]
    )
    assert alert.category == Alert.Category.SUSPICIOUS_URL
    assert alert.severity == Alert.Severity.WARNING


@pytest.mark.django_db
def test_suspicious_url_multiple_reasons_is_critical(device):
    alert = trigger_suspicious_url_alert(
        device,
        url="http://xn--pypal-4ve.ru/verify-login",
        title="",
        reasons=["domain punycode/homograph", "meniru domain 'paypal' tapi bukan domain resminya"],
    )
    assert alert.severity == Alert.Severity.CRITICAL


@pytest.mark.django_db
def test_suspicious_url_reuses_open_alert_instead_of_duplicating(device):
    first = trigger_suspicious_url_alert(
        device, url="http://192.168.1.50/a", title="", reasons=["host adalah alamat IP mentah"]
    )
    second = trigger_suspicious_url_alert(
        device, url="http://192.168.1.50/b", title="", reasons=["host adalah alamat IP mentah"]
    )
    assert second is None  # not "created" — the existing open alert was refreshed instead
    assert Alert.objects.filter(device=device, category=Alert.Category.SUSPICIOUS_URL).count() == 1
    assert Alert.objects.get(pk=first.pk).metadata["url"] == "http://192.168.1.50/b"
