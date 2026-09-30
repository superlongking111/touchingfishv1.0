"""Application icon loaded from bundled resources."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from fishmate.bootstrap import resource_path

_icon: QIcon | None = None


def app_icon() -> QIcon:
    global _icon
    if _icon is not None and not _icon.isNull():
        return _icon
    for name in ("app.ico", "app.png"):
        path = resource_path("resources", "icons", name)
        if path.is_file():
            ic = QIcon(str(path))
            if not ic.isNull():
                _icon = ic
                return _icon
    _icon = QIcon()
    return _icon


def apply_window_icon(window) -> None:
    ic = app_icon()
    if not ic.isNull():
        window.setWindowIcon(ic)
