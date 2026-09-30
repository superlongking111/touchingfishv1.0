"""System tray icon and menu."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from fishmate.ui.app_icon import app_icon

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class TrayController:
    def __init__(
        self,
        parent: "QWidget",
        on_open_big_fish: Callable,
        on_settings: Callable,
        on_toggle_pause: Callable,
        on_quit: Callable,
        icon: QIcon | None = None,
    ) -> None:
        tray_icon = icon if icon and not icon.isNull() else app_icon()
        self.tray = QSystemTrayIcon(tray_icon, parent)
        self._big_fish = False
        self._fish_paused = False
        self._update_tooltip()
        menu = QMenu(parent)
        act_big = QAction("打开摸大鱼", parent)
        act_big.triggered.connect(on_open_big_fish)
        act_settings = QAction("设置", parent)
        act_settings.triggered.connect(on_settings)
        self._pause_action = QAction("暂停摸鱼", parent)
        self._pause_action.triggered.connect(on_toggle_pause)
        act_quit = QAction("退出", parent)
        act_quit.triggered.connect(on_quit)
        menu.addAction(act_big)
        menu.addAction(act_settings)
        menu.addSeparator()
        menu.addAction(self._pause_action)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._activated)
        self._on_open = on_open_big_fish
        self.tray.show()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._on_open()

    def set_mode(self, big: bool) -> None:
        self._big_fish = big
        self._update_tooltip()

    def set_fish_paused(self, paused: bool) -> None:
        self._fish_paused = paused
        self._pause_action.setText("开启摸鱼" if paused else "暂停摸鱼")
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        if self._fish_paused:
            tip = "摸鱼助手 · 已暂停"
        elif self._big_fish:
            tip = "摸鱼助手 · 摸大鱼中"
        else:
            tip = "摸鱼助手 · 小摸鱼中"
        self.tray.setToolTip(tip)

    def show_message(self, title: str, body: str) -> None:
        self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 3000)
