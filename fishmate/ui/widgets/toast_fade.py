"""Shared fade / hover helpers for frameless toasts."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation, QRect, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QWidget

# 休息/内容弹窗：总展示时长含淡出；末段为渐隐
DEFAULT_TOAST_FADE_OUT_SEC = 4.0
DEFAULT_TOAST_DISPLAY_SEC = 10
TOAST_FADE_IN_MS = 250


def toast_hold_ms(display_seconds: int, fade_out_sec: float = DEFAULT_TOAST_FADE_OUT_SEC) -> int:
    """Milliseconds at full opacity before fade-out starts."""
    total = max(int(fade_out_sec) + 1, int(display_seconds))
    hold = total - fade_out_sec
    return max(0, int(hold * 1000))


def toast_fade_out_ms(fade_out_sec: float = DEFAULT_TOAST_FADE_OUT_SEC) -> int:
    return max(500, int(fade_out_sec * 1000))


def toast_card_contains_cursor(card: QFrame) -> bool:
    if not card.isVisible():
        return False
    tl = card.mapToGlobal(card.rect().topLeft())
    br = card.mapToGlobal(card.rect().bottomRight())
    return QRect(tl, br).normalized().contains(QCursor.pos())


def start_window_fade_in(host: QWidget, *, on_ready: Callable[[], None] | None = None) -> QPropertyAnimation:
    host.setWindowOpacity(0.0)
    anim = QPropertyAnimation(host, b"windowOpacity", host)
    anim.setDuration(TOAST_FADE_IN_MS)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_ready:
        anim.finished.connect(on_ready)
    anim.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return anim


def start_window_fade_out(
    host: QWidget,
    *,
    on_finished: Callable[[], None],
    duration_ms: int | None = None,
) -> QPropertyAnimation:
    ms = duration_ms if duration_ms is not None else toast_fade_out_ms()
    anim = QPropertyAnimation(host, b"windowOpacity", host)
    anim.setDuration(ms)
    anim.setStartValue(host.windowOpacity())
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    anim.finished.connect(on_finished)
    anim.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return anim


class FadeCountdown:
    """Hold at full opacity, then callback (start ~4s fade-out). Pauses on hover."""

    def __init__(
        self,
        host: QWidget,
        card: QFrame,
        *,
        display_seconds: int,
        on_timeout: Callable[[], None],
        fade_out_sec: float = DEFAULT_TOAST_FADE_OUT_SEC,
    ) -> None:
        self._host = host
        self._card = card
        self._display_seconds = max(int(fade_out_sec) + 1, int(display_seconds))
        self._fade_out_sec = fade_out_sec
        self._hold_ms = toast_hold_ms(self._display_seconds, fade_out_sec)
        self._on_timeout = on_timeout
        self._armed = False
        self._timer = QTimer(host)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._poll = QTimer(host)
        self._poll.setInterval(350)
        self._poll.timeout.connect(self._poll_hover)

    def arm(self) -> None:
        if self._armed:
            return
        self._armed = True
        self.restart()

    def restart(self) -> None:
        self._timer.stop()
        if toast_card_contains_cursor(self._card):
            self._poll.start()
            return
        self._poll.stop()
        self._timer.start(self._hold_ms)

    def stop(self) -> None:
        self._timer.stop()
        self._poll.stop()

    def _poll_hover(self) -> None:
        if not toast_card_contains_cursor(self._card):
            self._poll.stop()
            self.restart()

    def _on_timer(self) -> None:
        if toast_card_contains_cursor(self._card):
            self._poll.start()
            return
        self._on_timeout()
