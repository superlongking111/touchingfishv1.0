"""Windows current-user autostart via registry Run key."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("fishmate.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FishMate"


def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        if enabled:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"'
            else:
                app = Path(__file__).resolve().parents[1] / "app.py"
                cmd = f'"{sys.executable}" "{app}"'
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:  # noqa: BLE001
        logger.exception("autostart update failed")


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:  # noqa: BLE001
        return False
