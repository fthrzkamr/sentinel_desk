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
