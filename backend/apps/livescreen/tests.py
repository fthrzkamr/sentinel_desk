import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Permission, Role, User
from apps.audit.models import AuditLog
from apps.devices.models import Device, EnrollmentToken
from config.asgi import application


@pytest.fixture
def live_screen_role(db):
    role = Role.objects.create(name="LIVESCREEN_TEST")
    role.permissions.set([Permission.objects.create(code="monitoring.live_screen")])
    return role


@pytest.fixture
def admin_user(db, live_screen_role):
    return User.objects.create_user(
        username="ls_admin", email="ls_admin@example.com", password="StrongPass123!", role=live_screen_role
    )


@pytest.fixture
def enrolled_device(admin_user):
    token, raw_token = EnrollmentToken.create_with_token(created_by=admin_user, ttl_minutes=60)
    resp = APIClient().post("/api/agent/enroll/", {"token": raw_token, "hostname": "LAPTOP-LS"}, format="json")
    return resp.data["device_id"], resp.data["device_token"]


def _access_token_for(user):
    return str(RefreshToken.for_user(user).access_token)


@pytest.mark.django_db(transaction=True)
def test_agent_signal_rejects_invalid_token(enrolled_device):
    device_id, _ = enrolled_device

    async def run():
        communicator = WebsocketCommunicator(application, f"/ws/agent/{device_id}/signal/?token=wrong")
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_admin_signal_requires_permission(enrolled_device):
    device_id, _ = enrolled_device
    no_perm_user = User.objects.create_user(username="ls_noperm", email="ls_noperm@example.com", password="StrongPass123!")
    access = _access_token_for(no_perm_user)

    async def run():
        communicator = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_admin_signal_rejected_when_agent_offline(admin_user, enrolled_device):
    device_id, _ = enrolled_device
    access = _access_token_for(admin_user)

    async def run():
        communicator = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        connected, _ = await communicator.connect()
        assert connected is True  # accepted so it can deliver a clean error message
        message = await communicator.receive_json_from(timeout=5)
        assert message["type"] == "error"
        await communicator.disconnect()

    async_to_sync(run)()

    assert AuditLog.objects.filter(action="livescreen.start_failed", metadata__reason="agent_offline").exists()


@pytest.mark.django_db(transaction=True)
def test_relay_between_admin_and_agent_both_directions(admin_user, enrolled_device):
    device_id, device_token = enrolled_device
    access = _access_token_for(admin_user)

    async def run():
        agent_comm = WebsocketCommunicator(application, f"/ws/agent/{device_id}/signal/?token={device_token}")
        agent_connected, _ = await agent_comm.connect()
        assert agent_connected is True

        admin_comm = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        admin_connected, _ = await admin_comm.connect()
        assert admin_connected is True

        # agent should be told a viewer joined
        joined_msg = await agent_comm.receive_json_from(timeout=5)
        assert joined_msg["type"] == "viewer_joined"

        # admin -> agent
        await admin_comm.send_json_to({"type": "webrtc_offer", "sdp": "OFFER"})
        offer_msg = await agent_comm.receive_json_from(timeout=5)
        assert offer_msg == {"type": "webrtc_offer", "sdp": "OFFER"}

        # agent -> admin
        await agent_comm.send_json_to({"type": "webrtc_answer", "sdp": "ANSWER"})
        answer_msg = await admin_comm.receive_json_from(timeout=5)
        assert answer_msg == {"type": "webrtc_answer", "sdp": "ANSWER"}

        await admin_comm.disconnect()
        await agent_comm.disconnect()

    async_to_sync(run)()

    assert AuditLog.objects.filter(action="livescreen.started", device_id=device_id).exists()


@pytest.mark.django_db(transaction=True)
def test_second_admin_rejected_while_first_is_viewing(admin_user, enrolled_device):
    device_id, device_token = enrolled_device
    access = _access_token_for(admin_user)

    async def run():
        agent_comm = WebsocketCommunicator(application, f"/ws/agent/{device_id}/signal/?token={device_token}")
        await agent_comm.connect()

        first_admin = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        connected, _ = await first_admin.connect()
        assert connected is True
        await agent_comm.receive_json_from(timeout=5)  # viewer_joined

        second_admin = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        connected2, _ = await second_admin.connect()
        assert connected2 is True  # accepted so it can deliver a clean error before closing
        error_msg = await second_admin.receive_json_from(timeout=5)
        assert error_msg["type"] == "error"

        await first_admin.disconnect()
        await agent_comm.disconnect()
        await second_admin.disconnect()

    async_to_sync(run)()
