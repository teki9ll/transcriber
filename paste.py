"""Paste the clipboard into the currently focused window by simulating Ctrl+V.

Uses the Win32 keybd_event API through ctypes, so there are no extra
dependencies (and pynput is not required). On non-Windows systems it's a no-op.
"""
import ctypes
import sys

_IS_WINDOWS = sys.platform == "win32"

# Virtual-key codes / flags
_VK_CONTROL = 0x11
_VK_V = 0x56
_KEYEVENTF_KEYUP = 0x0002


def paste_clipboard() -> bool:
    """Send Ctrl+V to whatever window currently has focus. Returns True on success."""
    if not _IS_WINDOWS:
        return False
    try:
        u = ctypes.windll.user32
        u.keybd_event(_VK_CONTROL, 0, 0, 0)              # Ctrl down
        u.keybd_event(_VK_V, 0, 0, 0)                    # V down
        u.keybd_event(_VK_V, 0, _KEYEVENTF_KEYUP, 0)     # V up
        u.keybd_event(_VK_CONTROL, 0, _KEYEVENTF_KEYUP, 0)  # Ctrl up
        return True
    except Exception:
        return False
