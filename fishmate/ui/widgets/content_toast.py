"""Content fish toast: hover pauses fade, link title, browse ready queue."""



from __future__ import annotations



from html import escape

from typing import TYPE_CHECKING, Callable



from PySide6.QtCore import QAbstractAnimation, QPropertyAnimation, Qt, Signal

from PySide6.QtGui import QGuiApplication

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget



from fishmate.domain.content import content_display_blurb

from fishmate.repositories.content_repo import ContentItem

from fishmate.ui.style import toast_link_color, toast_stylesheet

from fishmate.ui.widgets.toast_fade import FadeCountdown, start_window_fade_in, start_window_fade_out



if TYPE_CHECKING:

    from fishmate.app_context import AppContext





class ContentFishToast(QWidget):

    """At most one auto-push; user can browse other ready items in-place."""



    closed = Signal(str)



    def __init__(

        self,

        ctx: AppContext,

        item: ContentItem,

        fade_seconds: int = 10,

        on_open_big: Callable[[], None] | None = None,

        parent: QWidget | None = None,

    ) -> None:

        super().__init__(parent)

        self._ctx = ctx

        self._on_open_big = on_open_big

        self._display_seconds = max(5, fade_seconds)

        self._acted = False

        self._fade_in_anim: QPropertyAnimation | None = None

        self._fade_out_anim: QPropertyAnimation | None = None

        self._fade_started = False

        self._current = item

        self._seen_ids: set[int] = {item.id}



        self.setWindowFlags(

            Qt.WindowType.FramelessWindowHint

            | Qt.WindowType.Tool

            | Qt.WindowType.WindowStaysOnTopHint

        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setMouseTracking(True)

        self._theme = str(ctx.settings.get("ui_theme") or "light")

        self.setStyleSheet(toast_stylesheet(self._theme))



        root = QFrame(self)

        root.setObjectName("Toast")

        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root.setMouseTracking(True)

        layout = QVBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(root)

        self._root = root



        inner = QVBoxLayout(root)

        inner.setContentsMargins(16, 14, 16, 14)



        self._title_lbl = QLabel()

        self._title_lbl.setObjectName("ToastTitle")

        self._title_lbl.setWordWrap(True)

        self._title_lbl.setOpenExternalLinks(True)

        self._title_lbl.setTextFormat(Qt.TextFormat.RichText)

        self._title_lbl.setTextInteractionFlags(

            Qt.TextInteractionFlag.TextBrowserInteraction

        )



        self._body_lbl = QLabel()

        self._body_lbl.setObjectName("ToastBody")

        self._body_lbl.setWordWrap(True)



        inner.addWidget(self._title_lbl)

        inner.addWidget(self._body_lbl)



        row = QHBoxLayout()

        self._next_btn = QPushButton("看看别的")

        self._next_btn.setObjectName("Ghost")

        self._next_btn.clicked.connect(self._show_next)

        big_btn = QPushButton("摸大鱼")

        big_btn.clicked.connect(self._open_big)

        close_btn = QPushButton("关闭")

        close_btn.setObjectName("Ghost")

        close_btn.clicked.connect(lambda: self._finish("dismiss"))

        row.addWidget(self._next_btn)

        row.addWidget(big_btn)

        row.addWidget(close_btn)

        inner.addLayout(row)



        self._countdown = FadeCountdown(

            self,

            self._root,

            display_seconds=self._display_seconds,

            on_timeout=self._fade_out,

        )



        self._apply_item(item)

        self._refresh_next_enabled()

        self.resize(380, 168)

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



    def current_item(self) -> ContentItem:

        return self._current



    def apply_ui_theme(self, theme: str) -> None:

        self._theme = str(theme or "light")

        self.setStyleSheet(toast_stylesheet(self._theme))

        self._apply_item(self._current)



    def _apply_item(self, item: ContentItem) -> None:

        self._current = item

        title, body = content_display_blurb(item)

        safe_url = escape(item.url, quote=True)

        safe_title = escape(title)

        link = toast_link_color(self._theme)

        self._title_lbl.setText(

            f'<a href="{safe_url}" style="color:{link};text-decoration:none;">'

            f"{safe_title}</a>"

        )

        self._body_lbl.setText(body)

        self.adjustSize()

        self._place()



    def _refresh_next_enabled(self) -> None:

        nxt = self._ctx.content.pick_random_portal_ready(self._seen_ids)

        self._next_btn.setEnabled(nxt is not None)

        if nxt is None:

            self._next_btn.setText("暂无其他")

        else:

            self._next_btn.setText("看看别的")



    def _show_next(self) -> None:

        prev = self._current

        self._ctx.content.set_status(prev.id, "dismissed")

        nxt = self._ctx.content.pick_random_portal_ready(self._seen_ids)

        if not nxt:

            self._refresh_next_enabled()

            return

        self._seen_ids.add(nxt.id)

        self._apply_item(nxt)

        self._ctx.content.set_status(nxt.id, "opened")

        self._refresh_next_enabled()

        self._countdown.restart()



    def _open_big(self) -> None:

        if self._on_open_big:

            self._on_open_big()

        self._finish("big_fish")



    def _place(self) -> None:

        screen = QGuiApplication.primaryScreen()

        if not screen:

            return

        geo = screen.availableGeometry()

        h = max(self.height(), 140)

        self.move(geo.right() - self.width() - 24, geo.bottom() - h - 24)



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

        cur = self._current

        if action in ("timeout", "dismiss") and cur:

            row = self._ctx.db.query_one(

                "SELECT status FROM content_items WHERE id=?", (cur.id,)

            )

            if row and row["status"] in ("pushed", "opened"):

                self._ctx.content.set_status(cur.id, "dismissed")

        self.closed.emit(action)

        self.hide()

        self.close()

