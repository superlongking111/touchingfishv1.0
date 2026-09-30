"""Fullscreen detection helpers for notification deferral."""

from __future__ import annotations

import sys


def is_fullscreen_app_active() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        # Near full screen coverage
        if width >= screen_w - 4 and height >= screen_h - 4:
            # Exclude desktop / shell
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
                return False
            return True
    except Exception:  # noqa: BLE001
        return False
    return False
