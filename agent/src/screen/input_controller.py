"""Native Windows Input Controller for Remote Control.
Simulates mouse movement, clicks, scrolling, keystrokes, shortcuts, and clipboard
using Windows Win32 APIs (user32.dll / SendInput / mouse_event / win32clipboard).
"""

import ctypes
import logging
import time
from ctypes import wintypes

import mss

logger = logging.getLogger("sentineldesk.agent")

# Windows constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Win32 64-bit / 32-bit compatible structures for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT),
    ]


# JavaScript Key/Code to Windows Virtual Key (VK) mapping
JS_CODE_TO_VK = {
    # Special keys
    "Backspace": 0x08,
    "Tab": 0x09,
    "Enter": 0x0D,
    "NumpadEnter": 0x0D,
    "ShiftLeft": 0x10,
    "ShiftRight": 0x10,
    "ControlLeft": 0x11,
    "ControlRight": 0x11,
    "AltLeft": 0x12,
    "AltRight": 0x12,
    "Pause": 0x13,
    "CapsLock": 0x14,
    "Escape": 0x1B,
    "Space": 0x20,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "End": 0x23,
    "Home": 0x24,
    "ArrowLeft": 0x25,
    "ArrowUp": 0x26,
    "ArrowRight": 0x27,
    "ArrowDown": 0x28,
    "PrintScreen": 0x2C,
    "Insert": 0x2D,
    "Delete": 0x2E,
    # Windows / Meta
    "MetaLeft": 0x5B,
    "MetaRight": 0x5C,
    "ContextMenu": 0x5D,
    # Function keys
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    # Symbols
    "Semicolon": 0xBA,
    "Equal": 0xBB,
    "Comma": 0xBC,
    "Minus": 0xBD,
    "Period": 0xBE,
    "Slash": 0xBF,
    "Backquote": 0xC0,
    "BracketLeft": 0xDB,
    "Backslash": 0xDC,
    "BracketRight": 0xDD,
    "Quote": 0xDE,
}

# Digits 0-9
for d in range(10):
    JS_CODE_TO_VK[f"Digit{d}"] = 0x30 + d
    JS_CODE_TO_VK[f"Numpad{d}"] = 0x60 + d

# Letters A-Z
for i in range(26):
    char = chr(ord("A") + i)
    JS_CODE_TO_VK[f"Key{char}"] = 0x41 + i


class InputController:
    """Handles translation and execution of remote control events into native Windows actions."""

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._sct = None
        self._monitors_cache = None
        self._last_cache_time = 0

    def _get_monitors(self):
        now = time.time()
        if not self._monitors_cache or (now - self._last_cache_time > 5):
            try:
                if self._sct is None:
                    factory = getattr(mss, "MSS", mss.mss)
                    self._sct = factory()
                self._monitors_cache = self._sct.monitors
                self._last_cache_time = now
            except Exception as exc:
                logger.debug("Failed to query monitors for input: %s", exc)
                return [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
        return self._monitors_cache

    def mouse_move(self, norm_x: float, norm_y: float, monitor_index: int = 1):
        """Move cursor using normalized coordinates [0.0, 1.0] relative to selected monitor."""
        try:
            monitors = self._get_monitors()
            idx = monitor_index
            if idx >= len(monitors) or idx < 0:
                idx = 1 if len(monitors) > 1 else 0

            mon = monitors[idx]
            abs_x = int(mon["left"] + norm_x * mon["width"])
            abs_y = int(mon["top"] + norm_y * mon["height"])

            self._user32.SetCursorPos(abs_x, abs_y)
        except Exception as exc:
            logger.debug("mouse_move error: %s", exc)

    def mouse_down(self, button: int = 0):
        """Button: 0=Left, 1=Middle, 2=Right."""
        try:
            flag = MOUSEEVENTF_LEFTDOWN
            if button == 1:
                flag = MOUSEEVENTF_MIDDLEDOWN
            elif button == 2:
                flag = MOUSEEVENTF_RIGHTDOWN
            self._user32.mouse_event(flag, 0, 0, 0, 0)
        except Exception as exc:
            logger.debug("mouse_down error: %s", exc)

    def mouse_up(self, button: int = 0):
        try:
            flag = MOUSEEVENTF_LEFTUP
            if button == 1:
                flag = MOUSEEVENTF_MIDDLEUP
            elif button == 2:
                flag = MOUSEEVENTF_RIGHTUP
            self._user32.mouse_event(flag, 0, 0, 0, 0)
        except Exception as exc:
            logger.debug("mouse_up error: %s", exc)

    def mouse_click(self, button: int = 0, norm_x: float | None = None, norm_y: float | None = None, monitor_index: int = 1):
        if norm_x is not None and norm_y is not None:
            self.mouse_move(norm_x, norm_y, monitor_index)
        self.mouse_down(button)
        time.sleep(0.01)
        self.mouse_up(button)

    def mouse_double_click(self, norm_x: float | None = None, norm_y: float | None = None, monitor_index: int = 1):
        self.mouse_click(0, norm_x, norm_y, monitor_index)
        time.sleep(0.05)
        self.mouse_click(0, norm_x, norm_y, monitor_index)

    def mouse_wheel(self, delta_y: float, delta_x: float = 0):
        try:
            # In JS wheel, positive deltaY means scrolling down (wheel down in Windows is negative)
            wheel_amount = int(-delta_y * 120) if abs(delta_y) < 10 else int(-delta_y)
            self._user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_amount, 0)
        except Exception as exc:
            logger.debug("mouse_wheel error: %s", exc)

    def key_down(self, key: str, code: str):
        vk = JS_CODE_TO_VK.get(code)
        if not vk and len(key) == 1:
            vk = self._user32.VkKeyScanW(ord(key)) & 0xFF

        if vk and vk > 0:
            try:
                self._user32.keybd_event(vk, 0, 0, 0)
            except Exception as exc:
                logger.debug("key_down error for %s (%s): %s", key, code, exc)
        else:
            # Fallback to typing character directly
            if len(key) == 1:
                self.type_text(key)

    def key_up(self, key: str, code: str):
        vk = JS_CODE_TO_VK.get(code)
        if not vk and len(key) == 1:
            vk = self._user32.VkKeyScanW(ord(key)) & 0xFF

        if vk and vk > 0:
            try:
                self._user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            except Exception as exc:
                logger.debug("key_up error for %s (%s): %s", key, code, exc)

    def type_text(self, text: str):
        """Types raw unicode characters via SendInput with KEYEVENTF_UNICODE."""
        if not text:
            return
        try:
            inputs = []
            for char in text:
                code_point = ord(char)
                # Key down
                ki_down = KEYBDINPUT(
                    wVk=0,
                    wScan=code_point,
                    dwFlags=KEYEVENTF_UNICODE,
                    time=0,
                    dwExtraInfo=0,
                )
                inp_down = INPUT(type=INPUT_KEYBOARD)
                inp_down.ki = ki_down
                inputs.append(inp_down)

                # Key up
                ki_up = KEYBDINPUT(
                    wVk=0,
                    wScan=code_point,
                    dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=0,
                )
                inp_up = INPUT(type=INPUT_KEYBOARD)
                inp_up.ki = ki_up
                inputs.append(inp_up)

            arr = (INPUT * len(inputs))(*inputs)
            self._user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        except Exception as exc:
            logger.debug("type_text error: %s", exc)

    def send_shortcut(self, shortcut: str):
        """Simulates common system shortcut combinations."""
        shortcut = shortcut.lower().strip()
        VK_LWIN = 0x5B
        VK_CONTROL = 0x11
        VK_SHIFT = 0x10
        VK_MENU = 0x12  # Alt
        VK_ESCAPE = 0x1B
        VK_TAB = 0x09

        try:
            if shortcut == "win_r":
                # Win + R (Run Dialog)
                self._user32.keybd_event(VK_LWIN, 0, 0, 0)
                self._user32.keybd_event(0x52, 0, 0, 0)  # R
                time.sleep(0.02)
                self._user32.keybd_event(0x52, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

            elif shortcut == "win_d":
                # Win + D (Toggle Desktop)
                self._user32.keybd_event(VK_LWIN, 0, 0, 0)
                self._user32.keybd_event(0x44, 0, 0, 0)  # D
                time.sleep(0.02)
                self._user32.keybd_event(0x44, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

            elif shortcut == "alt_tab":
                # Alt + Tab (Switch Window)
                self._user32.keybd_event(VK_MENU, 0, 0, 0)
                self._user32.keybd_event(VK_TAB, 0, 0, 0)
                time.sleep(0.02)
                self._user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            elif shortcut in ("task_mgr", "ctrl_shift_esc"):
                # Ctrl + Shift + Esc (Task Manager)
                self._user32.keybd_event(VK_CONTROL, 0, 0, 0)
                self._user32.keybd_event(VK_SHIFT, 0, 0, 0)
                self._user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                time.sleep(0.02)
                self._user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

            elif shortcut == "ctrl_c":
                self._user32.keybd_event(VK_CONTROL, 0, 0, 0)
                self._user32.keybd_event(0x43, 0, 0, 0)  # C
                time.sleep(0.02)
                self._user32.keybd_event(0x43, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

            elif shortcut == "ctrl_v":
                self._user32.keybd_event(VK_CONTROL, 0, 0, 0)
                self._user32.keybd_event(0x56, 0, 0, 0)  # V
                time.sleep(0.02)
                self._user32.keybd_event(0x56, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

            elif shortcut == "ctrl_a":
                self._user32.keybd_event(VK_CONTROL, 0, 0, 0)
                self._user32.keybd_event(0x41, 0, 0, 0)  # A
                time.sleep(0.02)
                self._user32.keybd_event(0x41, 0, KEYEVENTF_KEYUP, 0)
                self._user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        except Exception as exc:
            logger.debug("send_shortcut error for %s: %s", shortcut, exc)

    def set_clipboard(self, text: str):
        """Sets text into the target system's Windows clipboard."""
        try:
            import win32clipboard

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            logger.info("Remote clipboard updated with %d chars", len(text))
        except Exception as exc:
            logger.debug("set_clipboard error: %s", exc)

    def handle_control_event(self, event: dict, monitor_index: int = 1):
        """Main dispatcher for incoming control events."""
        action = event.get("action")
        if not action:
            return

        if action == "mouse_move":
            norm_x = event.get("x", 0.0)
            norm_y = event.get("y", 0.0)
            self.mouse_move(norm_x, norm_y, monitor_index)

        elif action == "mouse_down":
            button = event.get("button", 0)
            norm_x = event.get("x")
            norm_y = event.get("y")
            if norm_x is not None and norm_y is not None:
                self.mouse_move(norm_x, norm_y, monitor_index)
            self.mouse_down(button)

        elif action == "mouse_up":
            button = event.get("button", 0)
            norm_x = event.get("x")
            norm_y = event.get("y")
            if norm_x is not None and norm_y is not None:
                self.mouse_move(norm_x, norm_y, monitor_index)
            self.mouse_up(button)

        elif action == "mouse_click":
            button = event.get("button", 0)
            norm_x = event.get("x")
            norm_y = event.get("y")
            self.mouse_click(button, norm_x, norm_y, monitor_index)

        elif action == "mouse_double_click":
            norm_x = event.get("x")
            norm_y = event.get("y")
            self.mouse_double_click(norm_x, norm_y, monitor_index)

        elif action == "mouse_wheel":
            delta_y = event.get("delta_y", 0)
            delta_x = event.get("delta_x", 0)
            self.mouse_wheel(delta_y, delta_x)

        elif action == "key_down":
            self.key_down(event.get("key", ""), event.get("code", ""))

        elif action == "key_up":
            self.key_up(event.get("key", ""), event.get("code", ""))

        elif action == "type_text":
            self.type_text(event.get("text", ""))

        elif action == "shortcut":
            self.send_shortcut(event.get("shortcut", ""))

        elif action == "set_clipboard":
            self.set_clipboard(event.get("text", ""))
