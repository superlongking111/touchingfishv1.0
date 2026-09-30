"""Export wizard: select → check → generate → result (+ mail confirm)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fishmate.services.exporter import ExportService
from fishmate.services.mail import MailDraft
from fishmate.ui.style import apply_readable_theme
from fishmate.ui.widgets.async_workers import MailSendWorker

if TYPE_CHECKING:
    from fishmate.app_context import AppContext


class ExportWizard(QDialog):
    def __init__(self, ctx: "AppContext", summary_md: str = "", parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.summary_md = summary_md
        self.setWindowTitle("打包工作材料")
        apply_readable_theme(self, str(ctx.settings.get("ui_theme") or "light"))
        self.resize(680, 560)
        self.exporter = ExportService(ctx.path_policy)
        self.result = None
        self.export_id: int | None = None
        self._mail_worker: MailSendWorker | None = None

        layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.stack.addWidget(self._page_select())
        self.stack.addWidget(self._page_check())
        self.stack.addWidget(self._page_result())
        self.stack.addWidget(self._page_mail())

        nav = QHBoxLayout()
        self.back_btn = QPushButton("上一步")
        self.back_btn.clicked.connect(self._back)
        self.next_btn = QPushButton("下一步")
        self.next_btn.setObjectName("Primary")
        self.next_btn.clicked.connect(self._next)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        nav.addWidget(self.back_btn)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        nav.addWidget(close)
        layout.addLayout(nav)
        self._load_today_files()
        self._update_nav()

    def _page_select(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("选择要打包的文件（显式勾选，不会自动外发）"))
        quick = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(
            lambda: self._set_all_file_checks(Qt.CheckState.Checked)
        )
        self.select_none_btn = QPushButton("全不选")
        self.select_none_btn.clicked.connect(
            lambda: self._set_all_file_checks(Qt.CheckState.Unchecked)
        )
        self.invert_btn = QPushButton("反选")
        self.invert_btn.clicked.connect(self._invert_file_checks)
        quick.addWidget(self.select_all_btn)
        quick.addWidget(self.select_none_btn)
        quick.addWidget(self.invert_btn)
        quick.addStretch()
        self.file_sel_lbl = QLabel("")
        self.file_sel_lbl.setObjectName("Muted")
        quick.addWidget(self.file_sel_lbl)
        layout.addLayout(quick)
        self.file_list = QListWidget()
        self.file_list.itemChanged.connect(self._update_file_selection_label)
        layout.addWidget(self.file_list)
        row = QHBoxLayout()
        add = QPushButton("添加其他文件")
        add.clicked.connect(self._add_files)
        row.addWidget(add)
        layout.addLayout(row)
        self.include_worklog = QCheckBox("包含 worklog.json")
        self.include_worklog.setChecked(True)
        self.include_summary = QCheckBox("包含日报草稿 daily_summary.md")
        self.zip_name = QLineEdit(f"{datetime.now():%Y-%m-%d}_work.zip")
        form = QFormLayout()
        form.addRow(self.include_worklog)
        form.addRow(self.include_summary)
        form.addRow("ZIP 文件名", self.zip_name)
        layout.addLayout(form)
        return w

    def _page_check(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("检查文件状态"))
        self.check_list = QListWidget()
        layout.addWidget(self.check_list)
        self.size_lbl = QLabel("")
        layout.addWidget(self.size_lbl)
        return w

    def _page_result(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.result_lbl = QLabel("")
        self.result_lbl.setWordWrap(True)
        layout.addWidget(self.result_lbl)
        row = QHBoxLayout()
        open_dir = QPushButton("打开目录")
        open_dir.clicked.connect(self._open_dir)
        mail = QPushButton("发送邮件")
        mail.setObjectName("Primary")
        mail.clicked.connect(lambda: self.stack.setCurrentIndex(3) or self._update_nav())
        row.addWidget(open_dir)
        row.addWidget(mail)
        layout.addLayout(row)
        layout.addStretch()
        return w

    def _page_mail(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        warn = QLabel(
            "通过 SMTP 直接发送（设置 → 邮件里配置授权码）。"
            "请核对收件人、主题、正文与附件。"
        )
        warn.setObjectName("Headline")
        warn.setWordWrap(True)
        layout.addWidget(warn)
        form = QFormLayout()
        default_to = (
            self.ctx.settings.get("mail_smtp_to")
            or self.ctx.settings.get("mail_smtp_user")
            or ""
        )
        self.mail_to = QLineEdit(str(default_to))
        self.mail_subject = QLineEdit(f"工作材料 {datetime.now():%Y-%m-%d}")
        self.mail_body = QTextEdit()
        self.mail_body.setPlainText("请查收附件中的工作材料包。")
        form.addRow("收件人（逗号分隔）", self.mail_to)
        form.addRow("主题", self.mail_subject)
        form.addRow("正文", self.mail_body)
        layout.addLayout(form)
        self.attach_lbl = QLabel("")
        self.attach_lbl.setWordWrap(True)
        layout.addWidget(self.attach_lbl)
        self.sensitive_lbl = QLabel("")
        self.sensitive_lbl.setStyleSheet("color:#ffb4b4;")
        layout.addWidget(self.sensitive_lbl)
        send = QPushButton("确认发送邮件")
        send.setObjectName("Primary")
        send.clicked.connect(self._send_mail)
        self._mail_send_btn = send
        cancel = QPushButton("返回修改")
        cancel.clicked.connect(lambda: self.stack.setCurrentIndex(2) or self._update_nav())
        row = QHBoxLayout()
        row.addWidget(cancel)
        row.addWidget(send)
        layout.addLayout(row)
        return w

    def _set_all_file_checks(self, state: Qt.CheckState) -> None:
        self.file_list.blockSignals(True)
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(state)
        self.file_list.blockSignals(False)
        self._update_file_selection_label()

    def _invert_file_checks(self) -> None:
        self.file_list.blockSignals(True)
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setCheckState(
                Qt.CheckState.Unchecked
                if item.checkState() == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
        self.file_list.blockSignals(False)
        self._update_file_selection_label()

    def _update_file_selection_label(self, *_args) -> None:
        total = self.file_list.count()
        picked = sum(
            1
            for i in range(total)
            if self.file_list.item(i).checkState() == Qt.CheckState.Checked
        )
        self.file_sel_lbl.setText(f"已选 {picked} / {total}")

    def _load_today_files(self) -> None:
        self.file_list.clear()
        seen: set[str] = set()
        for e in self.ctx.worklog.events_for_day():
            if e.event_type == "DELETE":
                continue
            p = Path(e.path)
            if not p.exists() or not p.is_file():
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            item = QListWidgetItem(f"{p.name}  —  {p}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.file_list.addItem(item)
        self._update_file_selection_label()

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "添加文件")
        existing = {
            self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.file_list.count())
        }
        for f in files:
            key = str(Path(f).resolve())
            if key in existing:
                continue
            p = Path(f)
            item = QListWidgetItem(f"{p.name}  —  {p}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.file_list.addItem(item)
        self._update_file_selection_label()

    def _selected_paths(self) -> list[str]:
        paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                paths.append(item.data(Qt.ItemDataRole.UserRole))
        return paths

    def _run_check(self) -> None:
        self.check_list.clear()
        paths = self._selected_paths()
        checked = self.ctx.path_policy.validate_export_files(paths)
        total = 0
        for p, err in checked:
            try:
                size = p.stat().st_size if p.exists() and err is None else 0
            except OSError:
                size = 0
            total += size
            status = err or "OK"
            mtime = ""
            if err is None and p.exists():
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            self.check_list.addItem(
                f"[{status}] {p.name} | {size} bytes | {mtime} | {p}"
            )
        self.size_lbl.setText(f"预计约 {total / 1024:.1f} KB（压缩前）")
        self._checked = checked

    def _generate(self) -> bool:
        ok_files = [str(p) for p, e in self._checked if e is None]
        if not ok_files:
            QMessageBox.warning(self, "导出", "没有可打包的有效文件")
            return False
        events = self.ctx.worklog.events_for_day()
        worklog = [
            {
                "time": e.event_time,
                "type": e.event_type,
                "path": e.path,
                "sha256": e.sha256,
            }
            for e in events
        ]
        roots = [r.path for r in self.ctx.worklog.list_roots(enabled_only=True)]
        try:
            self.result = self.exporter.build_zip(
                ok_files,
                include_worklog=self.include_worklog.isChecked(),
                include_summary=self.include_summary.isChecked(),
                summary_md=self.summary_md,
                worklog_data=worklog,
                zip_name=self.zip_name.text().strip() or None,
                roots=roots,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))
            return False
        if not self.result.ok:
            QMessageBox.critical(self, "导出失败", self.result.error or "unknown")
            return False
        self.export_id = self.ctx.exports.add(
            self.result.zip_path,
            self.result.zip_sha256,
            len(self.result.files),
            self.result.total_bytes,
        )
        self.result_lbl.setText(
            f"已生成：\n{self.result.zip_path}\n\n"
            f"大小：{self.result.total_bytes} bytes\n"
            f"ZIP SHA-256：{self.result.zip_sha256}\n"
            f"文件数：{len(self.result.files)}\n"
            f"manifest 复验：通过"
        )
        # prepare mail attachment label
        zp = Path(self.result.zip_path)
        self.attach_lbl.setText(
            f"附件：{zp.name}（{zp.stat().st_size} bytes）\n路径：{zp}"
        )
        sensitive = self.ctx.settings.get("sensitive_extensions") or []
        hits = [
            f.path
            for f in self.result.files
            if any(f.path.lower().endswith(ext.lower()) for ext in sensitive)
        ]
        if hits:
            self.sensitive_lbl.setText(
                "警告：检测到敏感扩展名文件，请确认合规后再发送：\n" + "\n".join(hits)
            )
        else:
            self.sensitive_lbl.setText("")
        return True

    def _open_dir(self) -> None:
        if not self.result:
            return
        import subprocess
        import sys

        folder = str(Path(self.result.zip_path).parent)
        if sys.platform == "win32":
            subprocess.run(["explorer", folder], check=False)

    def _send_mail(self) -> None:
        if not self.result:
            return
        if self._mail_worker and self._mail_worker.isRunning():
            return
        to = [x.strip() for x in self.mail_to.text().split(",") if x.strip()]
        if not to:
            QMessageBox.warning(self, "邮件", "请填写收件人")
            return
        size = Path(self.result.zip_path).stat().st_size
        if size > 20 * 1024 * 1024:
            QMessageBox.warning(
                self,
                "附件过大",
                "附件可能超过常见邮件服务限制。请改为本地保存，或拆分后再发。",
            )
            return
        draft = MailDraft(
            to=to,
            subject=self.mail_subject.text().strip(),
            body=self.mail_body.toPlainText(),
            attachments=[self.result.zip_path],
        )
        self._mail_send_btn.setEnabled(False)
        self._mail_send_btn.setText("发送中…")
        self._mail_worker = MailSendWorker(self.ctx, draft)
        self._mail_worker.finished.connect(self._on_mail_sent)
        self._mail_worker.failed.connect(self._on_mail_failed)
        self._mail_worker.start()

    def _on_mail_sent(self, res) -> None:
        self._mail_send_btn.setEnabled(True)
        self._mail_send_btn.setText("确认发送邮件")
        if self.export_id:
            self.ctx.exports.update_mail_status(
                self.export_id, "sent_ok" if res.ok else "sent_fail"
            )
        if res.ok:
            QMessageBox.information(self, "邮件", res.message)
        else:
            QMessageBox.critical(self, "邮件", res.message)

    def _on_mail_failed(self, err: str) -> None:
        self._mail_send_btn.setEnabled(True)
        self._mail_send_btn.setText("确认发送邮件")
        QMessageBox.critical(self, "邮件", f"发送异常：{err}")

    def _next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 0:
            self._run_check()
            self.stack.setCurrentIndex(1)
        elif idx == 1:
            if self._generate():
                self.stack.setCurrentIndex(2)
        elif idx == 2:
            self.stack.setCurrentIndex(3)
        self._update_nav()

    def _back(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
        self._update_nav()

    def _update_nav(self) -> None:
        idx = self.stack.currentIndex()
        self.back_btn.setEnabled(idx > 0 and idx < 3)
        self.next_btn.setVisible(idx < 2)
        if idx == 0:
            self.next_btn.setText("检查")
        elif idx == 1:
            self.next_btn.setText("生成 ZIP")
