from unittest.mock import patch

import pytest
import requests
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.devices.models import EnrollmentToken
from apps.locations.models import Location
from apps.locations.services import estimate_location_from_ip


@pytest.fixture
def location_role(db):
    role = Role.objects.create(name="LOCATION_TEST")
    role.permissions.set([Permission.objects.create(code="location.view")])
    return role


@pytest.fixture
def admin_user(db, location_role):
    return User.objects.create_user(
        username="loc_admin", email="loc_admin@example.com", password="StrongPass123!", role=location_role
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "loc_admin", "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.fixture
def enrolled_device(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-LOC"}, format="json")
    return resp.data["device_id"], resp.data["device_token"]


def _post_location(device_id, device_token, payload=None):
    return APIClient().post(
        "/api/agent/location/",
        payload or {},
        format="json",
        HTTP_X_DEVICE_ID=device_id,
        HTTP_AUTHORIZATION=f"DeviceToken {device_token}",
    )


# --- estimate_location_from_ip (pure unit tests, no ingest endpoint involved) ---


def test_private_ip_returns_no_coordinates():
    result = estimate_location_from_ip("192.168.1.10")
    assert result == {"latitude": None, "longitude": None, "accuracy_meters": None}


def test_loopback_ip_returns_no_coordinates():
    result = estimate_location_from_ip("127.0.0.1")
    assert result["latitude"] is None


def test_invalid_ip_returns_no_coordinates():
    result = estimate_location_from_ip("not-an-ip")
    assert result["latitude"] is None


@patch("apps.locations.services.requests.get")
def test_successful_lookup_returns_coordinates(mock_get):
    mock_get.return_value.raise_for_status = lambda: None
    mock_get.return_value.json.return_value = {"status": "success", "lat": -6.2, "lon": 106.8}

    result = estimate_location_from_ip("8.8.8.8")

    assert result["latitude"] == -6.2
    assert result["longitude"] == 106.8
    assert result["accuracy_meters"] is not None


@patch("apps.locations.services.requests.get", side_effect=requests.RequestException("timeout"))
def test_lookup_failure_returns_no_coordinates(mock_get):
    result = estimate_location_from_ip("8.8.8.8")
    assert result == {"latitude": None, "longitude": None, "accuracy_meters": None}


# --- API endpoints ---


@pytest.mark.django_db
def test_agent_reports_os_location(enrolled_device):
    device_id, device_token = enrolled_device
    response = _post_location(device_id, device_token, {"latitude": -6.2, "longitude": 106.8, "accuracy_meters": 15})

    assert response.status_code == 201
    assert response.data["source"] == "OS"
    assert response.data["latitude"] == -6.2


@pytest.mark.django_db
def test_agent_without_os_location_falls_back_to_ip(enrolled_device):
    device_id, device_token = enrolled_device

    with patch("apps.locations.views.estimate_location_from_ip") as mock_estimate:
        mock_estimate.return_value = {"latitude": -6.9, "longitude": 107.6, "accuracy_meters": 5000}
        response = _post_location(device_id, device_token, {})

    assert response.status_code == 201
    assert response.data["source"] == "IP"
    assert response.data["latitude"] == -6.9


@pytest.mark.django_db
def test_ingest_rejects_latitude_without_longitude(enrolled_device):
    device_id, device_token = enrolled_device
    response = _post_location(device_id, device_token, {"latitude": -6.2})
    assert response.status_code == 400


@pytest.mark.django_db
def test_location_endpoints_require_permission(enrolled_device):
    device_id, device_token = enrolled_device
    _post_location(device_id, device_token, {"latitude": -6.2, "longitude": 106.8})

    no_perm_role = Role.objects.create(name="NO_LOC_PERM")
    viewer = User.objects.create_user(username="noperm3", email="noperm3@example.com", password="StrongPass123!")
    viewer.role = no_perm_role
    viewer.save()
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "noperm3", "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    assert client.get("/api/locations/").status_code == 403
    assert client.get(f"/api/devices/{device_id}/locations/").status_code == 403


@pytest.mark.django_db
def test_latest_location_returns_one_row_per_device(admin_client, enrolled_device):
    device_id, device_token = enrolled_device
    _post_location(device_id, device_token, {"latitude": -6.0, "longitude": 106.0})
    _post_location(device_id, device_token, {"latitude": -6.5, "longitude": 106.5})

    response = admin_client.get("/api/locations/")

    assert response.data["count"] == 1
    assert response.data["results"][0]["latitude"] == -6.5


@pytest.mark.django_db
def test_device_location_history_ordered_newest_first(admin_client, enrolled_device):
    device_id, device_token = enrolled_device
    _post_location(device_id, device_token, {"latitude": -6.0, "longitude": 106.0})
    _post_location(device_id, device_token, {"latitude": -6.5, "longitude": 106.5})

    response = admin_client.get(f"/api/devices/{device_id}/locations/")

    assert response.data["count"] == 2
    assert response.data["results"][0]["latitude"] == -6.5
    assert Location.objects.filter(device__device_id=device_id).count() == 2
