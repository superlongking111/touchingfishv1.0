"""Work timeline viewer."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from PySide6.QtCore import QDate

from fishmate.ui.style import apply_readable_theme

if TYPE_CHECKING:
    from fishmate.app_context import AppContext


class TimelineWindow(QDialog):
    def __init__(self, ctx: "AppContext", parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("工作时间线")
        apply_readable_theme(self, str(ctx.settings.get("ui_theme") or "light"))
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDate(QDate.currentDate())
        self.type = QComboBox()
        self.type.addItems(["全部", "CREATE", "MODIFY", "RENAME", "DELETE"])
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.reload)
        filters.addWidget(QLabel("日期"))
        filters.addWidget(self.date)
        filters.addWidget(QLabel("类型"))
        filters.addWidget(self.type)
        filters.addWidget(refresh)
        filters.addStretch()
        layout.addLayout(filters)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["时间", "类型", "路径", "大小", "SHA-256"])
        self.tree.setColumnWidth(0, 80)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 360)
        layout.addWidget(self.tree)

        row = QHBoxLayout()
        locate = QPushButton("定位文件")
        locate.clicked.connect(self._locate)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(locate)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)

        tip = QLabel("工作时间跨度仅表述首次/末次文件事件，不等同真实工时。")
        tip.setObjectName("Muted")
        layout.addWidget(tip)
        self.reload()

    def reload(self) -> None:
        self.tree.clear()
        d = self.date.date().toString("yyyy-MM-dd")
        t = self.type.currentText()
        et = None if t == "全部" else t
        events = self.ctx.worklog.list_events(date=d, event_type=et, limit=1000)
        for e in events:
            time_s = e.event_time[11:19] if len(e.event_time) >= 19 else e.event_time
            size_s = str(e.size) if e.size is not None else ""
            sha = (e.sha256 or "")[:12]
            item = QTreeWidgetItem([time_s, e.event_type, e.path, size_s, sha])
            item.setData(0, 256, e.path)  # Qt.UserRole
            self.tree.addTopLevelItem(item)
        first, last = self.ctx.worklog.span_for_day(d)
        if first and last:
            self.setWindowTitle(f"工作时间线 · 首末事件 {first[11:16]}–{last[11:16]}")

    def _locate(self) -> None:
        item = self.tree.currentItem()
        if not item:
            return
        path = item.data(0, 256)
        if not path or not Path(path).exists():
            return
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        else:
            os.startfile(str(Path(path).parent))  # type: ignore[attr-defined]
