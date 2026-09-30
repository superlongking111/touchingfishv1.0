"""In-app notice / confirm dialogs (replace native QMessageBox for key flows)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from fishmate.ui.style import apply_readable_theme, theme_from_widget


class NoticeDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        parent=None,
        *,
        detail: str | None = None,
        confirm: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        apply_readable_theme(self, theme_from_widget(parent))
        self.setMinimumWidth(380)
        self._confirmed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        head = QLabel(title)
        head.setObjectName("Headline")
        layout.addWidget(head)

        body = QLabel(message)
        body.setWordWrap(True)
        layout.addWidget(body)

        if detail:
            box = QTextEdit()
            box.setReadOnly(True)
            box.setPlainText(detail)
            box.setMinimumHeight(min(320, 80 + detail.count("\n") * 18))
            layout.addWidget(box)

        row = QHBoxLayout()
        row.addStretch()
        if confirm:
            cancel = QPushButton("取消")
            cancel.setObjectName("Ghost")
            cancel.clicked.connect(self.reject)
            ok = QPushButton("确定")
            ok.setObjectName("Primary")
            ok.clicked.connect(self._ok)
            row.addWidget(cancel)
            row.addWidget(ok)
        else:
            ok = QPushButton("知道了")
            ok.setObjectName("Primary")
            ok.clicked.connect(self._ok)
            row.addWidget(ok)
        layout.addLayout(row)

    def _ok(self) -> None:
        self._confirmed = True
        self.accept()

    @staticmethod
    def info(parent, title: str, message: str, detail: str | None = None) -> None:
        dlg = NoticeDialog(title, message, parent, detail=detail)
        dlg.exec()

    @staticmethod
    def saved(parent, message: str = "设置已保存") -> None:
        dlg = NoticeDialog("已保存", message, parent)
        dlg.exec()

    @staticmethod
    def confirm(parent, title: str, message: str) -> bool:
        dlg = NoticeDialog(title, message, parent, confirm=True)
        return dlg.exec() == QDialog.DialogCode.Accepted and dlg._confirmed
