"""Big Fish dashboard."""

from __future__ import annotations

import asyncio
import random
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fishmate.domain.content import (
    content_detail_text,
    content_display_blurb,
    content_list_preview,
)
from fishmate.domain.sessions import BigFishState
from fishmate.domain.worklog import events_to_llm_payload
from fishmate.ui.style import apply_readable_theme, panel_frame_stylesheet, normalize_theme

if TYPE_CHECKING:
    from fishmate.app_context import AppContext


class DurationDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, theme: str = "light") -> None:
        super().__init__(parent)
        self.setWindowTitle("开始摸大鱼")
        apply_readable_theme(self, theme)
        self.minutes: int | None = 10
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("选择摸鱼时长"))
        row = QHBoxLayout()
        for label, val in [("5 分钟", 5), ("10 分钟", 10), ("15 分钟", 15), ("不计时", None)]:
            btn = QPushButton(label)
            btn.setObjectName("Primary" if val == 10 else "")
            btn.clicked.connect(lambda checked=False, v=val: self._pick(v))
            row.addWidget(btn)
        layout.addLayout(row)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _pick(self, minutes: int | None) -> None:
        self.minutes = minutes
        self.accept()


class ContentDetailDialog(QDialog):
    def __init__(
        self,
        title: str,
        summary: str,
        reason: str,
        url: str,
        parent=None,
        *,
        theme: str = "light",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("内容详情")
        apply_readable_theme(self, theme)
        self.resize(480, 360)
        self.url = url
        self.uninterested = False
        layout = QVBoxLayout(self)
        t = QLabel(title)
        t.setObjectName("Headline")
        t.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(QLabel(f"为什么推荐：{reason or '—'}"))
        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(summary or "")
        layout.addWidget(body)
        row = QHBoxLayout()
        open_btn = QPushButton("打开原文")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self._open)
        no_btn = QPushButton("不感兴趣")
        no_btn.clicked.connect(self._no)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        row.addWidget(open_btn)
        row.addWidget(no_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _open(self) -> None:
        if self.url:
            webbrowser.open(self.url)
        self.accept()

    def _no(self) -> None:
        self.uninterested = True
        self.accept()


class ContentListDialog(QDialog):
    """本地内容池浏览（后台抓取入库，非现场联网）。"""

    def __init__(
        self,
        items: list,
        parent: QWidget | None = None,
        *,
        theme: str = "light",
        on_pick: Callable | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("内容库")
        apply_readable_theme(self, theme)
        self.resize(520, 480)
        self._by_id = {i.id: i for i in items}
        self._on_pick = on_pick
        layout = QVBoxLayout(self)
        tip = QLabel(
            "以下为后台定时抓取并写入本地的条目；托盘自动推送会优先用「今日话题」搜索摘要。"
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self._list = QListWidget()
        self._list.setUniformItemSizes(False)
        for item in items:
            preview = content_list_preview(item, max_len=20)
            row_w = QWidget()
            row_l = QVBoxLayout(row_w)
            row_l.setContentsMargins(10, 8, 10, 8)
            row_l.setSpacing(4)
            title_lbl = QLabel(item.title)
            title_lbl.setObjectName("Headline")
            title_lbl.setWordWrap(True)
            row_l.addWidget(title_lbl)
            if preview:
                prev_lbl = QLabel(preview)
                prev_lbl.setObjectName("Muted")
                prev_lbl.setWordWrap(True)
                row_l.addWidget(prev_lbl)
            row = QListWidgetItem()
            row.setData(Qt.ItemDataRole.UserRole, item.id)
            hint = row_w.sizeHint()
            row.setSizeHint(hint)
            self._list.addItem(row)
            self._list.setItemWidget(row, row_w)
        self._list.itemDoubleClicked.connect(self._open_item)
        layout.addWidget(self._list)
        row = QHBoxLayout()
        open_btn = QPushButton("查看选中")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self._open_selected)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        row.addWidget(open_btn)
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _open_selected(self) -> None:
        row = self._list.currentItem()
        if row:
            self._open_item(row)

    def _open_item(self, row: QListWidgetItem) -> None:
        item_id = row.data(Qt.ItemDataRole.UserRole)
        item = self._by_id.get(item_id)
        if item and self._on_pick:
            self._on_pick(item)


class DailyReportDialog(QDialog):
    def __init__(self, draft: str, parent=None, *, theme: str = "light") -> None:
        super().__init__(parent)
        self.setWindowTitle("日报草稿")
        apply_readable_theme(self, theme)
        self.resize(560, 480)
        layout = QVBoxLayout(self)
        tip = QLabel("【草稿】可编辑、复制，不会自动发送")
        tip.setObjectName("Muted")
        layout.addWidget(tip)
        self.editor = QTextEdit()
        self.editor.setPlainText(draft)
        layout.addWidget(self.editor)
        row = QHBoxLayout()
        copy_btn = QPushButton("复制")
        copy_btn.setObjectName("Primary")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        row.addWidget(copy_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _copy(self) -> None:
        self.editor.selectAll()
        self.editor.copy()

    def text(self) -> str:
        return self.editor.toPlainText()


class BigFishWindow(QMainWindow):
    request_end = Signal()
    request_export = Signal()
    request_timeline = Signal()
    request_settings = Signal()

    def __init__(
        self,
        ctx: "AppContext",
        state: BigFishState,
        on_ended: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.state = state
        self.on_ended = on_ended
        self._theme = normalize_theme(str(ctx.settings.get("ui_theme") or "light"))
        self.setWindowTitle("摸鱼助手 · 摸大鱼")
        apply_readable_theme(self, self._theme)
        self.resize(720, 640)
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._expired_notified = False
        self._refresh()

    def apply_ui_theme(self, theme: str) -> None:
        self._theme = normalize_theme(theme)
        apply_readable_theme(self, self._theme)
        self.content_frame.setStyleSheet(panel_frame_stylesheet(self._theme))

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(12)

        header = QHBoxLayout()
        brand = QLabel("摸大鱼")
        brand.setObjectName("Brand")
        self.clock_lbl = QLabel("")
        self.clock_lbl.setObjectName("Headline")
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(self.clock_lbl)
        layout.addLayout(header)

        self.timer_lbl = QLabel("")
        self.timer_lbl.setObjectName("Headline")
        layout.addWidget(self.timer_lbl)

        topic_row = QHBoxLayout()
        self.topic_lbl = QLabel("")
        self.topic_lbl.setObjectName("Muted")
        self.topic_lbl.setToolTip(
            "今日话题仅在「设置」里修改，用于资讯搜索抓取与托盘自动推送；"
            "摸大鱼随机/内容库主要来自门户浏览池，不按话题筛选。"
        )
        topic_row.addWidget(self.topic_lbl)
        topic_row.addStretch()
        for text, slot, tip in [
            (
                "随机来一条",
                self._random_content,
                "从本地已抓取内容里随机挑一条（不是点击时现抓）",
            ),
            (
                "浏览内容库",
                self._all_content,
                "查看本地池中的标题与摘要，双击可看详情",
            ),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            if tip:
                b.setToolTip(tip)
            topic_row.addWidget(b)
        layout.addLayout(topic_row)
        pool_hint = QLabel(
            "内容来自后台定时抓取入库。下方随机/内容库以门户热榜池为主；"
            "话题相关摘要由设置中的「今日话题」驱动搜索抓取，经托盘推送。"
        )
        pool_hint.setObjectName("Muted")
        pool_hint.setWordWrap(True)
        layout.addWidget(pool_hint)

        self.content_card = QLabel("暂无内容，去设置里添加来源或点「随机来一条」")
        self.content_card.setWordWrap(True)
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet(panel_frame_stylesheet(self._theme))
        fl = QVBoxLayout(self.content_frame)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.addWidget(self.content_card)
        layout.addWidget(self.content_frame)

        self.stats_lbl = QLabel("")
        layout.addWidget(self.stats_lbl)

        layout.addWidget(QLabel("工作痕迹"))
        self.trace_lbl = QLabel("")
        self.trace_lbl.setWordWrap(True)
        self.trace_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.trace_lbl, stretch=1)

        actions = QHBoxLayout()
        for text, slot in [
            ("工作痕迹时间线", self.request_timeline.emit),
            ("生成日报草稿", self._daily_report),
            ("打包工作材料", self.request_export.emit),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            actions.addWidget(b)
        layout.addLayout(actions)

        end_row = QHBoxLayout()
        end_btn = QPushButton("结束摸大鱼")
        end_btn.setObjectName("Danger")
        end_btn.clicked.connect(lambda: self._end("user"))
        more_btn = QPushButton("再摸 5 分钟")
        more_btn.setObjectName("Primary")
        more_btn.clicked.connect(self._extend)
        end_row.addStretch()
        end_row.addWidget(more_btn)
        end_row.addWidget(end_btn)
        layout.addLayout(end_row)

    def _tick(self) -> None:
        self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S"))
        rem = self.state.remaining_seconds()
        if rem is None:
            self.timer_lbl.setText("不计时摸鱼中")
        else:
            m, s = divmod(rem, 60)
            self.timer_lbl.setText(f"剩余 {m:02d}:{s:02d}")
            if rem <= 0 and not self._expired_notified:
                self._expired_notified = True
                self._on_timer_end()
        if datetime.now().second % 15 == 0:
            self._refresh_traces()

    def _refresh(self) -> None:
        topic = self.ctx.settings.get("today_topic") or "（未设置）"
        self.topic_lbl.setText(f"今日话题：{topic}")
        stats = self.ctx.reminders.stats_today()
        sess = self.ctx.sessions.today_stats()
        self.stats_lbl.setText(
            f"今日摸鱼：喝水{stats.get('water',0)} 走动{stats.get('walk',0)} "
            f"厕所{stats.get('toilet',0)} 休息{stats.get('rest_minutes',0)}min · "
            f"摸大鱼 {sess.get('count',0)} 次 / {sess.get('minutes',0)} 分钟"
        )
        self._refresh_traces()
        self._tick()

    def _refresh_traces(self) -> None:
        events = self.ctx.worklog.events_for_day()
        if not events:
            first, last = self.ctx.worklog.span_for_day()
            self.trace_lbl.setText("今天还没有文件事件。可在设置中添加工作目录。")
            return
        lines = []
        for e in events[-8:]:
            t = e.event_time[11:16] if len(e.event_time) >= 16 else e.event_time
            name = Path(e.path).name
            lines.append(f"{t}  {e.event_type}  {name}")
        first, last = self.ctx.worklog.span_for_day()
        span = ""
        if first and last:
            span = f"\n首次/末次文件事件：{first[11:16]} – {last[11:16]}（非真实工时）"
        self.trace_lbl.setText("\n".join(lines) + span)

    def _on_timer_end(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("差不多得了")
        box.setText("摸大鱼时间到了")
        end_btn = box.addButton("结束摸大鱼", QMessageBox.ButtonRole.AcceptRole)
        more_btn = box.addButton("再摸 5 分钟", QMessageBox.ButtonRole.ActionRole)
        box.exec()
        if box.clickedButton() == more_btn:
            self._extend()
        else:
            self._end("timer")

    def _extend(self) -> None:
        self.state.extend(5)
        if self.state.session_id:
            self.ctx.sessions.extend(self.state.session_id, 5)
        self._expired_notified = False

    def _end(self, reason: str) -> None:
        self._timer.stop()
        self.on_ended(reason)
        self.close()

    def _random_content(self) -> None:
        item = self.ctx.content.pick_random_ready()
        if not item:
            item = self.ctx.content.pick_random_portal_ready()
        if not item:
            cands = self.ctx.content.list_by_status("candidate", 20)
            item = random.choice(cands) if cands else None
        if not item:
            pushed = self.ctx.content.list_by_status("pushed", 20)
            item = random.choice(pushed) if pushed else None
        if not item:
            self.content_card.setText(
                "本地还没有内容。请在设置里配置来源与话题，或点「立即抓取」等待入库。"
            )
            return
        self.content_card.setText(
            f"捕获到一条鱼\n{item.title}\n"
            f"{content_display_blurb(item)[1]}"
        )
        self._open_content_detail(item)

    def _open_content_detail(self, item) -> None:
        dlg = ContentDetailDialog(
            item.title,
            content_detail_text(item),
            item.llm_reason or "",
            item.url,
            self,
            theme=self._theme,
        )
        dlg.exec()
        if dlg.uninterested:
            self.ctx.content.set_status(item.id, "dismissed")
        elif item.status == "ready":
            self.ctx.content.set_status(item.id, "opened")

    def _all_content(self) -> None:
        items = self.ctx.content.list_browse_pool(80)
        if not items:
            QMessageBox.information(
                self, "内容库", "暂无内容。后台抓取完成后会出现在这里。"
            )
            return

        dlg = ContentListDialog(
            items,
            self,
            theme=self._theme,
            on_pick=self._open_content_detail,
        )
        dlg.exec()

    def _daily_report(self) -> None:
        notes, ok = QInputDialog.getMultiLineText(
            self, "补充说明", "可选补充说明（不读取文件正文）："
        )
        if not ok:
            return
        date = datetime.now().strftime("%Y-%m-%d")
        events = self.ctx.worklog.events_for_day(date)
        payload = events_to_llm_payload(events, notes, date)
        client = self.ctx.build_llm_client()
        draft = ""
        if client and client.api_key:
            try:
                draft = asyncio.run(client.draft_daily_report(payload, notes))
            except Exception as exc:  # noqa: BLE001
                draft = self._local_draft(payload, notes, fallback=str(type(exc).__name__))
        else:
            draft = self._local_draft(payload, notes)
        dlg = DailyReportDialog(draft, self, theme=self._theme)
        dlg.exec()
        self._last_summary = dlg.text()

    def _local_draft(self, payload: dict, notes: str, fallback: str = "") -> str:
        lines = ["【草稿】日报（本地聚合，未调用模型）", ""]
        if fallback:
            lines.append(f"（模型不可用：{fallback}）")
            lines.append("")
        lines.append("## 完成")
        seen = set()
        for e in payload.get("events", []):
            key = e["path"]
            if key in seen:
                continue
            seen.add(key)
            if e["type"] in ("CREATE", "MODIFY"):
                lines.append(f"- {e['path']}（{e['type']} @ {e['time']}）")
        lines.append("")
        lines.append("## 进行中")
        lines.append("- （根据文件事件自行补充）")
        lines.append("")
        lines.append("## 待处理")
        lines.append("- （待补充）")
        if notes:
            lines.append("")
            lines.append("## 备注")
            lines.append(notes)
        return "\n".join(lines)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Closing window ends big fish (return to small fish)
        if self._timer.isActive():
            self._timer.stop()
            self.on_ended("close")
        event.accept()
