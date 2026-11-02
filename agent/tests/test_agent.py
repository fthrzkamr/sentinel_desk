import sys
from pathlib import Path

# Ensure agent/src is on sys.path
AGENT_SRC = str(Path(__file__).resolve().parent.parent / "src")
if AGENT_SRC not in sys.path:
    sys.path.insert(0, AGENT_SRC)

import pytest
from services.updater import is_newer_version
from networking.client import get_session
from screen.capture_track import get_available_monitors


def test_updater_is_newer_version():
    # is_newer_version(candidate, current)
    assert is_newer_version("0.8.1", "0.8.0") is True
    assert is_newer_version("0.9.0", "0.8.0") is True
    assert is_newer_version("1.0.0", "0.8.0") is True
    assert is_newer_version("0.8.0", "0.8.1") is False
    assert is_newer_version("0.8.0", "0.8.0") is False
    assert is_newer_version("0.8.1", "invalid") is True


def test_networking_session_pool():
    session = get_session()
    assert session is not None
    # Reusing session should yield the exact same instance
    assert get_session() is session
    # Verify adapter mounts
    assert "http://" in session.adapters
    assert "https://" in session.adapters


def test_get_available_monitors():
    monitors = get_available_monitors()
    assert isinstance(monitors, list)
    assert len(monitors) >= 1
    for m in monitors:
        assert "index" in m
        assert "name" in m
        assert "width" in m
        assert "height" in m
        assert m["width"] > 0
        assert m["height"] > 0


def test_input_controller_event_dispatch():
    from screen.input_controller import InputController, JS_CODE_TO_VK

    ctrl = InputController()
    assert ctrl is not None
    assert JS_CODE_TO_VK["Enter"] == 0x0D
    assert JS_CODE_TO_VK["KeyA"] == 0x41
    assert JS_CODE_TO_VK["Digit1"] == 0x31

    # Dispatch mouse and keyboard events (defensive execution)
    ctrl.handle_control_event({"action": "mouse_move", "x": 0.5, "y": 0.5}, monitor_index=1)
    ctrl.handle_control_event({"action": "mouse_down", "button": 0, "x": 0.5, "y": 0.5}, monitor_index=1)
    ctrl.handle_control_event({"action": "mouse_up", "button": 0, "x": 0.5, "y": 0.5}, monitor_index=1)
    ctrl.handle_control_event({"action": "mouse_wheel", "delta_y": -100, "delta_x": 0}, monitor_index=1)
    ctrl.handle_control_event({"action": "key_down", "key": "Enter", "code": "Enter"})
    ctrl.handle_control_event({"action": "key_up", "key": "Enter", "code": "Enter"})
    ctrl.handle_control_event({"action": "type_text", "text": "Hello SentinelDesk"})
    ctrl.handle_control_event({"action": "shortcut", "shortcut": "win_d"})


