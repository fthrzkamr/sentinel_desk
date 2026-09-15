import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, User
from apps.audit.models import AuditLog


@pytest.fixture
def viewer_role(db):
    role = Role.objects.create(name="VIEWER")
    perm = Permission.objects.create(code="device.view", description="View devices")
    role.permissions.add(perm)
    return role


@pytest.fixture
def user(db, viewer_role):
    return User.objects.create_user(
        username="alice", email="alice@example.com", password="StrongPass123!", role=viewer_role
    )


@pytest.mark.django_db
def test_login_success_returns_tokens_and_user(user):
    client = APIClient()
    response = client.post(
        "/api/auth/login/", {"username": "alice", "password": "StrongPass123!"}, format="json"
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["user"]["username"] == "alice"
    assert response.data["user"]["permissions"] == ["device.view"]
    assert AuditLog.objects.filter(action="auth.login", user=user).exists()


@pytest.mark.django_db
def test_login_invalid_credentials_is_rejected_and_audited(user):
    client = APIClient()
    response = client.post(
        "/api/auth/login/", {"username": "alice", "password": "wrong-password"}, format="json"
    )

    assert response.status_code == 401
    assert AuditLog.objects.filter(action="auth.login_failed").exists()


@pytest.mark.django_db
def test_me_endpoint_requires_authentication():
    client = APIClient()
    response = client.get("/api/auth/me/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_me_endpoint_returns_current_user(user):
    client = APIClient()
    login = client.post(
        "/api/auth/login/", {"username": "alice", "password": "StrongPass123!"}, format="json"
    )
    access = login.data["access"]

    response = client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {access}")

    assert response.status_code == 200
    assert response.data["username"] == "alice"


@pytest.mark.django_db
def test_has_permission_code_respects_role(user):
    assert user.has_permission_code("device.view") is True
    assert user.has_permission_code("user.manage") is False


@pytest.mark.django_db
def test_superuser_has_every_permission(db):
    admin = User.objects.create_superuser(
        username="root", email="root@example.com", password="StrongPass123!"
    )
    assert admin.has_permission_code("user.manage") is True


@pytest.fixture
def user_manager_role(db):
    role = Role.objects.create(name="USER_MANAGER")
    role.permissions.set([Permission.objects.get_or_create(code="user.manage")[0]])
    return role


@pytest.fixture
def user_manager(db, user_manager_role):
    return User.objects.create_user(
        username="umanager", email="umanager@example.com", password="StrongPass123!", role=user_manager_role
    )


def _client_for(username):
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.mark.django_db
def test_non_manager_cannot_list_users(user):
    response = _client_for("alice").get("/api/users/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_can_list_and_create_user(user_manager, viewer_role):
    client = _client_for("umanager")

    listing = client.get("/api/users/")
    assert listing.status_code == 200

    create = client.post(
        "/api/users/",
        {
            "username": "newbie",
            "email": "newbie@example.com",
            "password": "AnotherStrongPass456!",
            "role": viewer_role.id,
        },
        format="json",
    )
    assert create.status_code == 201
    assert create.data["username"] == "newbie"
    assert User.objects.filter(username="newbie").exists()
    assert AuditLog.objects.filter(action="user.created").exists()


@pytest.mark.django_db
def test_created_user_can_log_in_with_chosen_password(user_manager, viewer_role):
    client = _client_for("umanager")
    client.post(
        "/api/users/",
        {"username": "newbie2", "email": "newbie2@example.com", "password": "AnotherStrongPass456!", "role": viewer_role.id},
        format="json",
    )
    login = APIClient().post(
        "/api/auth/login/", {"username": "newbie2", "password": "AnotherStrongPass456!"}, format="json"
    )
    assert login.status_code == 200


@pytest.mark.django_db
def test_weak_password_rejected_on_create(user_manager):
    client = _client_for("umanager")
    response = client.post(
        "/api/users/", {"username": "weakpass", "email": "weak@example.com", "password": "123"}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_manager_can_update_role_and_deactivate_other_user(user_manager, user, viewer_role):
    client = _client_for("umanager")

    patch = client.patch(f"/api/users/{user.id}/", {"role": None}, format="json")
    assert patch.status_code == 200
    assert patch.data["role"] is None
    assert AuditLog.objects.filter(action="user.updated").exists()

    deactivate = client.post(f"/api/users/{user.id}/deactivate/")
    assert deactivate.status_code == 200
    user.refresh_from_db()
    assert user.is_active is False
    assert AuditLog.objects.filter(action="user.deactivated").exists()

    activate = client.post(f"/api/users/{user.id}/activate/")
    assert activate.status_code == 200
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_manager_cannot_deactivate_own_account(user_manager):
    client = _client_for("umanager")
    response = client.post(f"/api/users/{user_manager.id}/deactivate/")
    assert response.status_code == 400
    user_manager.refresh_from_db()
    assert user_manager.is_active is True


@pytest.mark.django_db
def test_manager_can_reset_another_users_password(user_manager, user):
    client = _client_for("umanager")
    response = client.post(f"/api/users/{user.id}/reset-password/", {"new_password": "BrandNewPass789!"}, format="json")
    assert response.status_code == 204
    assert AuditLog.objects.filter(action="user.password_reset").exists()

    login = APIClient().post("/api/auth/login/", {"username": "alice", "password": "BrandNewPass789!"}, format="json")
    assert login.status_code == 200


@pytest.mark.django_db
def test_role_list_requires_user_manage_permission(user_manager, user):
    assert _client_for("umanager").get("/api/roles/").status_code == 200
    assert _client_for("alice").get("/api/roles/").status_code == 403
