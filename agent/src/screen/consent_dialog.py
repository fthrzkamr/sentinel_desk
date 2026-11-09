"""Native Windows consent dialog for incoming remote sessions.
Shows a modal system dialog on the client screen with 'Setujui' and 'Tolak' buttons.
Automatically times out and rejects if there is no response within 30 seconds.
"""

import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger("sentineldesk.agent")

WH_CBT = 5
HCBT_ACTIVATE = 5
IDYES = 6
IDNO = 7
MB_YESNO = 0x00000004
MB_ICONQUESTION = 0x00000020
MB_TOPMOST = 0x00040000
MB_SETFOREGROUND = 0x00010000
MB_SYSTEMMODAL = 0x00001000

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


def ask_remote_permission(timeout_seconds: int = 30) -> bool:
    """Displays a native modal dialog on the client screen asking to approve or deny remote access.
    Renames the buttons to 'Setujui' and 'Tolak'.
    Returns True if user clicks 'Setujui', False if 'Tolak' or timeout.
    """
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.SetDlgItemTextW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LPCWSTR]
        user32.SetDlgItemTextW.restype = wintypes.BOOL

        user32.MessageBoxTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.UINT,
            wintypes.WORD,
            wintypes.DWORD,
        ]
        user32.MessageBoxTimeoutW.restype = ctypes.c_int

        h_hook = None

        def cbt_proc(n_code, w_param, l_param):
            if n_code == HCBT_ACTIVATE:
                try:
                    user32.SetDlgItemTextW(w_param, IDYES, "Setujui")
                    user32.SetDlgItemTextW(w_param, IDNO, "Tolak")
                except Exception:
                    pass
            return user32.CallNextHookEx(h_hook, n_code, w_param, l_param)

        c_callback = HOOKPROC(cbt_proc)
        h_hook = user32.SetWindowsHookExW(WH_CBT, c_callback, None, kernel32.GetCurrentThreadId())

        message = (
            "Permintaan Akses & Kendali Remote Masuk\n\n"
            "Administrator SentinelDesk sedang meminta izin untuk melihat layar dan mengendalikan perangkat ini secara remote.\n\n"
            "Apakah Anda menyetujui sesi remote ini?\n"
            "(Permintaan otomatis ditolak jika tidak ada respons dalam 30 detik)"
        )
        caption = "SentinelDesk - Izin Remote Masuk"
        flags = MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND | MB_SYSTEMMODAL

        res = user32.MessageBoxTimeoutW(0, message, caption, flags, 0, int(timeout_seconds * 1000))

        if h_hook:
            user32.UnhookWindowsHookEx(h_hook)

        logger.info("Remote permission dialog result: %s", res)
        return res == IDYES
    except Exception as exc:
        logger.warning("Error displaying permission dialog: %s", exc)
        return False

