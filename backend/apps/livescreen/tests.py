import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Permission, Role, User
from apps.audit.models import AuditLog
from apps.devices.models import Device, EnrollmentToken
from apps.system_settings.models import SystemSettings
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
        agent_connected, _ = await agent_comm.connect(timeout=5)
        assert agent_connected is True

        admin_comm = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        admin_connected, _ = await admin_comm.connect(timeout=5)
        assert admin_connected is True

        # admin receives ice_config on connect
        ice_config_msg = await admin_comm.receive_json_from(timeout=5)
        assert ice_config_msg["type"] == "ice_config"
        assert "ice_servers" in ice_config_msg

        # agent should be told a viewer joined with ice_servers
        joined_msg = await agent_comm.receive_json_from(timeout=5)
        assert joined_msg["type"] == "viewer_joined"
        assert "ice_servers" in joined_msg

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


@pytest.mark.django_db
def test_livescreen_status_endpoint_returns_ice_servers(admin_user, enrolled_device):
    device_id, _ = enrolled_device
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_access_token_for(admin_user)}")

    resp = client.get(f"/api/devices/{device_id}/live-screen-status/")
    assert resp.status_code == 200
    assert resp.data["device_id"] == device_id
    assert "ice_servers" in resp.data
    assert resp.data["ice_servers"][0]["urls"] == ["stun:stun.l.google.com:19302"]

    # Configure TURN in SystemSettings
    settings = SystemSettings.get_solo()
    settings.turn_server_enabled = True
    settings.turn_server_url = "turn:turn.sentineldesk.internal:3478"
    settings.turn_username = "sentinel"
    settings.turn_credential = "secretpassword"
    settings.save()

    resp = client.get(f"/api/devices/{device_id}/live-screen-status/")
    assert resp.status_code == 200
    ice_servers = resp.data["ice_servers"]
    assert len(ice_servers) == 2
    assert ice_servers[1]["urls"] == ["turn:turn.sentineldesk.internal:3478"]
    assert ice_servers[1]["username"] == "sentinel"
    assert ice_servers[1]["credential"] == "secretpassword"


@pytest.mark.django_db(transaction=True)
def test_relay_monitors_list_and_switch_monitor(admin_user, enrolled_device):
    device_id, device_token = enrolled_device
    access = _access_token_for(admin_user)

    async def run():
        agent_comm = WebsocketCommunicator(application, f"/ws/agent/{device_id}/signal/?token={device_token}")
        agent_connected, _ = await agent_comm.connect(timeout=5)
        assert agent_connected is True

        admin_comm = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        admin_connected, _ = await admin_comm.connect(timeout=5)
        assert admin_connected is True

        await admin_comm.receive_json_from(timeout=5)  # ice_config
        await agent_comm.receive_json_from(timeout=5)  # viewer_joined

        # agent sends monitors_list -> admin receives
        monitors_payload = [
            {"index": 1, "name": "Monitor 1 (1920x1080)"},
            {"index": 2, "name": "Monitor 2 (1920x1080)"},
        ]
        await agent_comm.send_json_to({"type": "monitors_list", "monitors": monitors_payload})
        monitors_msg = await admin_comm.receive_json_from(timeout=5)
        assert monitors_msg["type"] == "monitors_list"
        assert monitors_msg["monitors"] == monitors_payload

        # admin sends switch_monitor -> agent receives
        await admin_comm.send_json_to({"type": "switch_monitor", "monitor_index": 2})
        switch_msg = await agent_comm.receive_json_from(timeout=5)
        assert switch_msg["type"] == "switch_monitor"
        assert switch_msg["monitor_index"] == 2

        # agent sends monitor_switched ack -> admin receives
        await agent_comm.send_json_to({"type": "monitor_switched", "monitor_index": 2})
        switched_ack = await admin_comm.receive_json_from(timeout=5)
        assert switched_ack["type"] == "monitor_switched"
        assert switched_ack["monitor_index"] == 2

        await admin_comm.disconnect()
        await agent_comm.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_remote_control_toggle_audited(admin_user, enrolled_device):
    from apps.audit.models import AuditLog

    device_id, device_token = enrolled_device
    access = _access_token_for(admin_user)

    async def run():
        agent_comm = WebsocketCommunicator(application, f"/ws/agent/{device_id}/signal/?token={device_token}")
        agent_connected, _ = await agent_comm.connect(timeout=5)
        assert agent_connected is True

        admin_comm = WebsocketCommunicator(application, f"/ws/livescreen/{device_id}/?token={access}")
        admin_connected, _ = await admin_comm.connect(timeout=5)
        assert admin_connected is True

        await admin_comm.receive_json_from(timeout=5)  # ice_config
        await agent_comm.receive_json_from(timeout=5)  # viewer_joined

        # Admin enables remote control
        await admin_comm.send_json_to({"type": "remote_control_toggle", "enabled": True})
        # Admin disables remote control
        await admin_comm.send_json_to({"type": "remote_control_toggle", "enabled": False})

        await admin_comm.disconnect()
        await agent_comm.disconnect()

    async_to_sync(run)()

    assert AuditLog.objects.filter(action="livescreen.control_enabled", device_id=device_id).exists()
    assert AuditLog.objects.filter(action="livescreen.control_disabled", device_id=device_id).exists()

