"""Global Qt styles — light / dark themes."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

# Shared structure; colors swapped per theme
_LIGHT = {
    "bg": "#ffffff",
    "bg_alt": "#fafafa",
    "bg_tab": "#f0f0f0",
    "bg_header": "#f5f5f5",
    "text": "#111111",
    "text_muted": "#444444",
    "border": "#dddddd",
    "border_input": "#cccccc",
    "primary_bg": "#111111",
    "primary_fg": "#ffffff",
    "hover_btn": "#f5f5f5",
    "highlight": "#333333",
    "placeholder": "#888888",
    "toast_border": "#666666",
    "tooltip_bg": "#111111",
    "tooltip_fg": "#ffffff",
}

_DARK = {
    "bg": "#1e1e1e",
    "bg_alt": "#252526",
    "bg_tab": "#2d2d2d",
    "bg_header": "#333333",
    "text": "#e8e8e8",
    "text_muted": "#aaaaaa",
    "border": "#3c3c3c",
    "border_input": "#555555",
    "primary_bg": "#e8e8e8",
    "primary_fg": "#1e1e1e",
    "hover_btn": "#2a2a2a",
    "highlight": "#569cd6",
    "placeholder": "#888888",
    "toast_border": "#555555",
    "tooltip_bg": "#e8e8e8",
    "tooltip_fg": "#1e1e1e",
}


def _build_app_qss(c: dict[str, str]) -> str:
    return f"""
QWidget {{
    background-color: {c["bg"]};
    color: {c["text"]};
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {c["bg"]};
    color: {c["text"]};
}}

QLabel {{
    background-color: transparent;
    color: {c["text"]};
}}

QLabel#Brand {{
    font-size: 24px;
    font-weight: 700;
    color: {c["text"]};
}}

QLabel#Headline {{
    font-size: 16px;
    font-weight: 600;
    color: {c["text"]};
}}

QLabel#Muted {{
    color: {c["text_muted"]};
    font-size: 12px;
}}

QLabel#FieldLabel {{
    color: {c["text"]};
    font-size: 12px;
    font-weight: 600;
    padding-top: 8px;
}}

QPushButton {{
    background-color: {c["bg"]};
    color: {c["text"]};
    border: 1px solid {c["border_input"]};
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 22px;
}}

QPushButton:hover {{
    background-color: {c["hover_btn"]};
    border-color: {c["text_muted"]};
}}

QPushButton#Primary {{
    background-color: {c["primary_bg"]};
    color: {c["primary_fg"]};
    border: 1px solid {c["primary_bg"]};
    font-weight: 600;
}}

QPushButton#Primary:hover {{
    opacity: 0.9;
}}

QPushButton#Ghost {{
    background-color: {c["bg"]};
    color: {c["text_muted"]};
    border: 1px solid {c["border_input"]};
}}

QPushButton#Danger {{
    background-color: {c["bg"]};
    color: #f48771;
    border: 1px solid #f48771;
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background-color: {c["bg_alt"]};
    color: {c["text"]};
    border: 1px solid {c["border_input"]};
    border-radius: 6px;
    padding: 8px 10px;
    selection-background-color: {c["highlight"]};
    selection-color: {c["primary_fg"]};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {c["text_muted"]};
}}

QLineEdit::placeholder {{
    color: {c["placeholder"]};
}}

QListWidget, QTreeWidget {{
    background-color: {c["bg_alt"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    alternate-background-color: {c["bg"]};
}}

QTabWidget::pane {{
    border: 1px solid {c["border"]};
    background-color: {c["bg"]};
}}

QTabBar::tab {{
    background-color: {c["bg_tab"]};
    color: {c["text_muted"]};
    padding: 8px 14px;
    border: 1px solid {c["border"]};
    border-bottom: none;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {c["bg"]};
    color: {c["text"]};
    font-weight: 600;
}}

QCheckBox, QRadioButton {{
    color: {c["text"]};
    background: transparent;
}}

QScrollArea {{
    border: none;
    background-color: {c["bg"]};
}}

QScrollArea > QWidget > QWidget {{
    background-color: {c["bg"]};
}}

QGroupBox {{
    border: 1px solid {c["border"]};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    background-color: {c["bg"]};
    color: {c["text"]};
}}

QGroupBox::title {{
    color: {c["text"]};
    font-weight: 600;
}}

QHeaderView::section {{
    background-color: {c["bg_header"]};
    color: {c["text"]};
    padding: 6px;
    border: 1px solid {c["border"]};
}}

QMessageBox {{
    background-color: {c["bg"]};
    color: {c["text"]};
}}

QToolTip {{
    background-color: {c["tooltip_bg"]};
    color: {c["tooltip_fg"]};
    border: none;
    padding: 6px;
}}
"""


def _build_toast_qss(c: dict[str, str], *, link: str) -> str:
    return f"""
QWidget {{
    background-color: {c["bg"]};
    color: {c["text"]};
}}
QFrame#Toast {{
    background-color: {c["bg"]};
    border: 1px solid {c["toast_border"]};
    border-radius: 10px;
}}
QLabel#ToastTitle {{
    color: {link};
    font-size: 14px;
    font-weight: 700;
    background: transparent;
}}
QLabel#ToastBody {{
    color: {c["text_muted"]};
    font-size: 13px;
    background: transparent;
}}
QPushButton {{
    background-color: {c["primary_bg"]};
    color: {c["primary_fg"]};
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton#Ghost {{
    background-color: {c["bg"]};
    color: {c["text_muted"]};
    border: 1px solid {c["border_input"]};
}}
"""


APP_QSS = _build_app_qss(_LIGHT)
APP_QSS_DARK = _build_app_qss(_DARK)
TOAST_QSS = _build_toast_qss(_LIGHT, link="#111111")
TOAST_QSS_DARK = _build_toast_qss(_DARK, link="#9cdcfe")


def normalize_theme(name: str | None) -> str:
    return "dark" if (name or "").strip().lower() == "dark" else "light"


def app_stylesheet(theme: str) -> str:
    return APP_QSS_DARK if normalize_theme(theme) == "dark" else APP_QSS


def toast_stylesheet(theme: str) -> str:
    return TOAST_QSS_DARK if normalize_theme(theme) == "dark" else TOAST_QSS


def toast_link_color(theme: str) -> str:
    return "#9cdcfe" if normalize_theme(theme) == "dark" else "#111111"


def panel_frame_stylesheet(theme: str) -> str:
    theme = normalize_theme(theme)
    c = _DARK if theme == "dark" else _LIGHT
    return (
        f'QFrame {{ background-color: {c["bg_alt"]}; '
        f'border: 1px solid {c["border"]}; border-radius: 8px; }}'
    )


def theme_from_widget(widget: QWidget | None) -> str:
    w = widget
    while w is not None:
        t = getattr(w, "_theme", None)
        if t is not None:
            return normalize_theme(str(t))
        ctx = getattr(w, "ctx", None)
        if ctx is not None and getattr(ctx, "settings", None) is not None:
            return normalize_theme(str(ctx.settings.get("ui_theme") or "light"))
        w = w.parent()
    return "light"


def apply_app_theme(app: QApplication, theme: str) -> None:
    theme = normalize_theme(theme)
    c = _DARK if theme == "dark" else _LIGHT
    p = QPalette()
    bg = QColor(c["bg"])
    text = QColor(c["text"])
    p.setColor(QPalette.ColorRole.Window, bg)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, QColor(c["bg_alt"]))
    p.setColor(QPalette.ColorRole.AlternateBase, bg)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, bg)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, text)
    p.setColor(QPalette.ColorRole.Highlight, QColor(c["highlight"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(c["primary_fg"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["tooltip_bg"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(c["tooltip_fg"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["placeholder"]))
    app.setPalette(p)
    app.setStyleSheet(app_stylesheet(theme))


def apply_readable_theme(widget: QWidget, theme: str = "light") -> None:
    from fishmate.ui.app_icon import apply_window_icon

    theme = normalize_theme(theme)
    widget.setStyleSheet(app_stylesheet(theme))
    widget.setAutoFillBackground(True)
    apply_window_icon(widget)
    c = _DARK if theme == "dark" else _LIGHT
    pal = widget.palette()
    bg = QColor(c["bg"])
    text = QColor(c["text"])
    for role in (
        QPalette.ColorRole.Window,
        QPalette.ColorRole.Base,
        QPalette.ColorRole.Button,
        QPalette.ColorRole.AlternateBase,
    ):
        pal.setColor(role, bg)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        pal.setColor(role, text)
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["highlight"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(c["primary_fg"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["placeholder"]))
    widget.setPalette(pal)
