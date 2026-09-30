"""Bottom-right toast with fade-out."""



from __future__ import annotations



from typing import Callable



from PySide6.QtCore import QAbstractAnimation, QPropertyAnimation, Qt, Signal

from PySide6.QtGui import QGuiApplication

from PySide6.QtWidgets import (

    QFrame,

    QHBoxLayout,

    QLabel,

    QPushButton,

    QVBoxLayout,

    QWidget,

)



from fishmate.ui.style import normalize_theme, toast_stylesheet

from fishmate.ui.widgets.toast_fade import FadeCountdown, start_window_fade_in, start_window_fade_out





class ToastNotification(QWidget):

    closed = Signal(str)  # action



    def __init__(

        self,

        title: str,

        body: str,

        primary_text: str = "好的",

        snooze_text: str = "稍后 10 分钟",

        fade_seconds: int = 10,

        on_primary: Callable | None = None,

        on_snooze: Callable | None = None,

        parent: QWidget | None = None,

        theme: str = "light",

    ) -> None:

        super().__init__(parent)

        self._theme = normalize_theme(theme)

        self.setWindowFlags(

            Qt.WindowType.FramelessWindowHint

            | Qt.WindowType.Tool

            | Qt.WindowType.WindowStaysOnTopHint

        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._on_primary = on_primary

        self._on_snooze = on_snooze

        self._display_seconds = max(5, fade_seconds)

        self._acted = False

        self._fade_started = False

        self._fade_in_anim: QPropertyAnimation | None = None

        self._fade_out_anim: QPropertyAnimation | None = None



        self.setStyleSheet(toast_stylesheet(self._theme))

        root = QFrame(self)

        root.setObjectName("Toast")

        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root.setMouseTracking(True)

        self.setMouseTracking(True)

        self._root = root

        layout = QVBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(root)



        inner = QVBoxLayout(root)

        inner.setContentsMargins(16, 14, 16, 14)

        title_lbl = QLabel(title)

        title_lbl.setObjectName("ToastTitle")

        body_lbl = QLabel(body)

        body_lbl.setObjectName("ToastBody")

        body_lbl.setWordWrap(True)

        inner.addWidget(title_lbl)

        inner.addWidget(body_lbl)



        row = QHBoxLayout()

        primary = QPushButton(primary_text)

        primary.clicked.connect(self._primary)

        snooze = QPushButton(snooze_text)

        snooze.setObjectName("Ghost")

        snooze.clicked.connect(self._snooze)

        close_btn = QPushButton("关闭")

        close_btn.setObjectName("Ghost")

        close_btn.clicked.connect(lambda: self._finish("dismiss"))

        row.addWidget(primary)

        row.addWidget(snooze)

        row.addWidget(close_btn)

        inner.addLayout(row)



        self._countdown = FadeCountdown(

            self,

            self._root,

            display_seconds=self._display_seconds,

            on_timeout=self._fade_out,

        )



        self.resize(340, 140)

        self._place()



    def showEvent(self, event) -> None:  # noqa: N802

        super().showEvent(event)

        if self._fade_started:

            return

        self._fade_started = True

        self._fade_in_anim = start_window_fade_in(self, on_ready=self._countdown.arm)

        self.raise_()



    def show(self) -> None:

        super().show()

        self.raise_()



    def apply_ui_theme(self, theme: str) -> None:

        self._theme = normalize_theme(theme)

        self.setStyleSheet(toast_stylesheet(self._theme))



    def _place(self) -> None:

        screen = QGuiApplication.primaryScreen()

        if not screen:

            return

        geo = screen.availableGeometry()

        self.move(geo.right() - self.width() - 24, geo.bottom() - self.height() - 24)



    def _primary(self) -> None:

        try:

            if self._on_primary:

                self._on_primary()

        finally:

            self._finish("primary")



    def _snooze(self) -> None:

        try:

            if self._on_snooze:

                self._on_snooze()

        finally:

            self._finish("snooze")



    def _fade_out(self) -> None:

        self._countdown.stop()

        if self._fade_out_anim and self._fade_out_anim.state() == QPropertyAnimation.State.Running:

            return

        self._fade_out_anim = start_window_fade_out(

            self,

            on_finished=lambda: self._finish("timeout"),

        )



    def _finish(self, action: str) -> None:

        if self._acted:

            return

        self._acted = True

        self._countdown.stop()

        for anim in (self._fade_in_anim, self._fade_out_anim):

            if anim and anim.state() == QAbstractAnimation.State.Running:

                anim.stop()

        self.setWindowOpacity(1.0)

        self.closed.emit(action)

        self.hide()

        self.close()

