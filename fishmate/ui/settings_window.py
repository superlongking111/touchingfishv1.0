"""Settings window: general / reminders / content / model / worklog."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from fishmate.domain.topic import TOPIC_SEPARATOR_HINT, topic_display_summary
from fishmate.repositories.reminder_repo import Reminder
from fishmate.security.secrets import SecretStore
from fishmate.services.content_cycle import ContentCycleReport
from fishmate.ui.style import apply_readable_theme
from fishmate.services.mail.smtp_client import SmtpMailClient
from fishmate.ui.widgets.async_workers import ContentFetchWorker, LlmTestWorker, MailTestWorker
from fishmate.ui.widgets.notice_dialog import NoticeDialog

if TYPE_CHECKING:
    from fishmate.app_context import AppContext


class SettingsWindow(QDialog):
    def __init__(
        self,
        ctx: "AppContext",
        on_changed: Callable | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.on_changed = on_changed
        self._llm_worker: LlmTestWorker | None = None
        self._fetch_worker: ContentFetchWorker | None = None
        self._mail_test_worker: MailTestWorker | None = None
        self.setWindowTitle("摸鱼助手 · 设置")
        self._theme = str(ctx.settings.get("ui_theme") or "light")
        apply_readable_theme(self, self._theme)
        self.resize(680, 580)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "通用")
        tabs.addTab(self._reminders_tab(), "提醒")
        tabs.addTab(self._content_tab(), "内容")
        tabs.addTab(self._model_tab(), "模型")
        tabs.addTab(self._mail_tab(), "邮件")
        tabs.addTab(self._work_tab(), "工作痕迹")
        layout.addWidget(tabs)
        row = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._save)
        close = QPushButton("关闭")
        close.setObjectName("Ghost")
        close.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(close)
        row.addWidget(self.save_btn)
        layout.addLayout(row)

    def _general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.ui_theme = QComboBox()
        self.ui_theme.addItem("浅色", "light")
        self.ui_theme.addItem("深色", "dark")
        current = str(self.ctx.settings.get("ui_theme") or "light")
        idx = self.ui_theme.findData(current)
        self.ui_theme.setCurrentIndex(idx if idx >= 0 else 0)
        self.autostart = QCheckBox("开机自动启动")
        self.autostart.setChecked(bool(self.ctx.settings.get("autostart")))
        self.fade = QSpinBox()
        self.fade.setRange(5, 60)
        self.fade.setValue(int(self.ctx.settings.get("notification_fade_seconds", 10)))
        self.fullscreen = QCheckBox("全屏时延后提醒")
        self.fullscreen.setChecked(bool(self.ctx.settings.get("defer_when_fullscreen", True)))
        self.retention = QSpinBox()
        self.retention.setRange(7, 365)
        self.retention.setValue(int(self.ctx.settings.get("data_retention_days", 90)))
        clear_btn = QPushButton("清空本地统计")
        clear_btn.clicked.connect(self._clear_stats)
        form.addRow("界面主题", self.ui_theme)
        form.addRow(self.autostart)
        form.addRow("通知展示（秒，末 4 秒淡出）", self.fade)
        form.addRow(self.fullscreen)
        form.addRow("数据保留（天）", self.retention)
        form.addRow(clear_btn)
        return w

    def _reminders_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.reminder_list = QListWidget()
        self._reload_reminders()
        layout.addWidget(self.reminder_list)
        row = QHBoxLayout()
        add_btn = QPushButton("新增提醒")
        add_btn.clicked.connect(self._add_reminder)
        edit = QPushButton("编辑选中")
        edit.clicked.connect(self._edit_reminder)
        row.addWidget(add_btn)
        row.addWidget(edit)
        layout.addLayout(row)
        tip = QLabel(
            "支持间隔型与固定时间型；可开关、有效时段、随机扰动与文案。"
            "修改后保存会立即按新间隔重新计时。"
        )
        tip.setObjectName("Muted")
        layout.addWidget(tip)
        return w

    def _reload_reminders(self) -> None:
        self.reminder_list.clear()
        self._reminder_objs = self.ctx.reminders.list_all()
        for r in self._reminder_objs:
            flag = "✓" if r.enabled else "✗"
            sched = (
                f"每{r.interval_minutes}分±{r.jitter_minutes}"
                if r.schedule_type == "interval"
                else ",".join(r.fixed_times)
            )
            self.reminder_list.addItem(f"[{flag}] {r.name} · {sched} · {r.message}")

    def _reminder_form_dialog(
        self,
        title: str,
        *,
        initial: Reminder | None = None,
        allow_schedule_type: bool = False,
    ) -> Reminder | None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        apply_readable_theme(dlg, self._theme)
        form = QFormLayout(dlg)
        enabled = QCheckBox("启用")
        enabled.setChecked(initial.enabled if initial else True)
        name = QLineEdit(initial.name if initial else "")
        msg = QLineEdit(initial.message if initial else "")
        sched = QComboBox()
        sched.addItem("间隔（分钟）", "interval")
        sched.addItem("固定时刻", "fixed")
        if initial:
            idx = sched.findData(initial.schedule_type)
            sched.setCurrentIndex(idx if idx >= 0 else 0)
            if not allow_schedule_type:
                sched.setEnabled(False)
        interval = QSpinBox()
        interval.setRange(1, 24 * 60)
        interval.setValue(initial.interval_minutes if initial and initial.interval_minutes else 45)
        jitter = QSpinBox()
        jitter.setRange(0, 60)
        jitter.setValue(initial.jitter_minutes if initial else 0)
        fixed = QLineEdit(",".join(initial.fixed_times) if initial else "10:30,15:30")
        win = initial.active_window if initial else {"start": "09:00", "end": "19:00"}
        win_start = QLineEdit(win.get("start", "09:00"))
        win_end = QLineEdit(win.get("end", "19:00"))
        win_start.setPlaceholderText("09:00")
        win_end.setPlaceholderText("19:00")

        form.addRow(enabled)
        form.addRow("名称", name)
        form.addRow("文案", msg)
        if allow_schedule_type:
            form.addRow("调度方式", sched)
        form.addRow("间隔（分钟）", interval)
        form.addRow("随机扰动（分钟）", jitter)
        form.addRow("固定时间（逗号分隔）", fixed)
        form.addRow("有效时段起", win_start)
        form.addRow("有效时段止", win_end)
        save = QPushButton("保存")
        form.addRow(save)

        result: Reminder | None = None

        def sync_schedule_fields() -> None:
            is_interval = sched.currentData() == "interval"
            interval.setEnabled(is_interval)
            jitter.setEnabled(is_interval)
            fixed.setEnabled(not is_interval)

        if allow_schedule_type:
            sched.currentIndexChanged.connect(sync_schedule_fields)
        sync_schedule_fields()

        def do_save() -> None:
            nonlocal result
            n = name.text().strip()
            if not n:
                NoticeDialog.info(dlg, "提示", "请填写名称")
                return
            st = str(sched.currentData() if allow_schedule_type else (initial.schedule_type if initial else "interval"))
            window = {
                "start": win_start.text().strip() or "09:00",
                "end": win_end.text().strip() or "19:00",
            }
            if initial:
                result = Reminder(
                    id=initial.id,
                    type=initial.type,
                    name=n,
                    enabled=enabled.isChecked(),
                    schedule_type=st,
                    interval_minutes=interval.value() if st == "interval" else None,
                    fixed_times=[x.strip() for x in fixed.text().split(",") if x.strip()]
                    if st == "fixed"
                    else [],
                    jitter_minutes=jitter.value(),
                    active_window=window,
                    message=msg.text().strip() or n,
                )
            else:
                result = Reminder(
                    id=0,
                    type="custom",
                    name=n,
                    enabled=enabled.isChecked(),
                    schedule_type=st,
                    interval_minutes=interval.value() if st == "interval" else None,
                    fixed_times=[x.strip() for x in fixed.text().split(",") if x.strip()]
                    if st == "fixed"
                    else [],
                    jitter_minutes=jitter.value(),
                    active_window=window,
                    message=msg.text().strip() or n,
                )
            dlg.accept()

        save.clicked.connect(do_save)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return result

    def _notify_reminders_changed(self) -> None:
        if self.on_changed:
            self.on_changed({"reminders_changed": True})

    def _edit_reminder(self) -> None:
        idx = self.reminder_list.currentRow()
        if idx < 0:
            NoticeDialog.info(self, "提示", "请先选中一条提醒")
            return
        r = self._reminder_objs[idx]
        updated = self._reminder_form_dialog(f"编辑 · {r.name}", initial=r)
        if not updated:
            return
        self.ctx.reminders.update(updated)
        self._reload_reminders()
        self._notify_reminders_changed()

    def _add_reminder(self) -> None:
        draft = self._reminder_form_dialog("新增提醒", allow_schedule_type=True)
        if not draft:
            return
        self.ctx.reminders.create_custom(
            draft.name,
            draft.message,
            draft.schedule_type,
            interval_minutes=draft.interval_minutes,
            fixed_times=draft.fixed_times,
            jitter_minutes=draft.jitter_minutes,
            active_window=draft.active_window,
        )
        self._reload_reminders()
        self._notify_reminders_changed()

    def _content_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        self.topic = QLineEdit(self.ctx.settings.get("today_topic") or "")
        self.topic.setPlaceholderText("例如：AI Agent，大模型 / 自动化")
        layout.addWidget(QLabel("今日话题"))
        layout.addWidget(self.topic)

        hint = QLabel(TOPIC_SEPARATOR_HINT)
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(
            QLabel(
                "来源：主题资讯搜索（弹窗主推）+ B站/新浪/头条/ACG17（看看别的）"
            )
        )
        self.source_list = QListWidget()
        self._reload_sources()
        layout.addWidget(self.source_list, stretch=1)

        row1 = QHBoxLayout()
        restore = QPushButton("恢复默认来源")
        restore.setObjectName("Ghost")
        restore.clicked.connect(self._restore_sources)
        test_src = QPushButton("测试选中来源")
        test_src.clicked.connect(self._test_selected_source)
        self.fetch_btn = QPushButton("立即抓取并筛选")
        self.fetch_btn.setObjectName("Primary")
        self.fetch_btn.clicked.connect(self._fetch_and_rank)
        for b in (restore, test_src, self.fetch_btn):
            row1.addWidget(b)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        add_rss = QPushButton("添加 RSS")
        add_rss.clicked.connect(lambda: self._add_source("rss"))
        add_web = QPushButton("添加网页")
        add_web.clicked.connect(lambda: self._add_source("web"))
        add_json = QPushButton("添加 JSON")
        add_json.clicked.connect(lambda: self._add_source("json"))
        add_search = QPushButton("添加搜索")
        add_search.clicked.connect(lambda: self._add_source("search"))
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self._del_source)
        for b in (add_rss, add_web, add_json, add_search, del_btn):
            row2.addWidget(b)
        layout.addLayout(row2)

        self.fetch_status = QLabel("")
        self.fetch_status.setObjectName("Muted")
        self.fetch_status.setWordWrap(True)
        layout.addWidget(self.fetch_status)

        form = QFormLayout()
        self.fetch_min = QSpinBox()
        self.fetch_min.setRange(5, 240)
        self.fetch_min.setValue(int(self.ctx.settings.get("content_fetch_min_minutes", 35)))
        self.fetch_max = QSpinBox()
        self.fetch_max.setRange(5, 240)
        self.fetch_max.setValue(int(self.ctx.settings.get("content_fetch_max_minutes", 90)))
        self.daily_limit = QSpinBox()
        self.daily_limit.setRange(1, 50)
        self.daily_limit.setValue(int(self.ctx.settings.get("content_daily_limit", 6)))
        form.addRow("抓取随机间隔（分）", self.fetch_min)
        form.addRow("抓取随机间隔（分）上限", self.fetch_max)
        form.addRow("每日推送上限", self.daily_limit)
        layout.addLayout(form)
        return w

    def _reload_sources(self) -> None:
        self.source_list.clear()
        self._sources = self.ctx.content.list_sources()
        if not self._sources:
            self.source_list.addItem("（暂无来源，请点「恢复默认来源」）")
        for s in self._sources:
            flag = "✓" if s.enabled else "✗"
            self.source_list.addItem(f"[{flag}] {s.name} · {s.type} · {s.url}")

    def _restore_sources(self) -> None:
        removed, added = self.ctx.content.refresh_preset_sources()
        self._reload_sources()
        if removed == 0 and added == 0:
            NoticeDialog.info(
                self,
                "内容来源",
                "当前已是默认来源，无需变更。",
            )
            return
        parts = []
        if removed:
            parts.append(f"已移除 {removed} 个旧预设")
        if added:
            parts.append(f"已添加 {added} 个新预设")
        NoticeDialog.info(
            self,
            "已恢复默认来源",
            " · ".join(parts) + "。\n可在列表中禁用或删除不需要的站点。",
        )

    def _selected_source_id(self) -> int | None:
        idx = self.source_list.currentRow()
        if idx < 0 or not self._sources or idx >= len(self._sources):
            return None
        return self._sources[idx].id

    def _set_fetch_busy(self, busy: bool, hint: str = "") -> None:
        self.fetch_btn.setEnabled(not busy)
        self.fetch_status.setText(hint)

    def _fetch_and_rank(self) -> None:
        self._persist_content_settings_only()
        if self._fetch_worker and self._fetch_worker.isRunning():
            return
        self._set_fetch_busy(True, "正在后台抓取并筛选，界面不会卡住…")
        self._fetch_worker = ContentFetchWorker(self.ctx, rank=True)
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.failed.connect(self._on_fetch_failed)
        self._fetch_worker.start()

    def _test_selected_source(self) -> None:
        sid = self._selected_source_id()
        if sid is None:
            NoticeDialog.info(self, "测试来源", "请先在列表中选中一个来源。")
            return
        if self._fetch_worker and self._fetch_worker.isRunning():
            return
        self._set_fetch_busy(True, "正在测试选中来源（仅拉取，不调用模型）…")
        self._fetch_worker = ContentFetchWorker(
            self.ctx, only_source_id=sid, rank=False
        )
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.failed.connect(self._on_fetch_failed)
        self._fetch_worker.start()

    def _on_fetch_done(self, report: ContentCycleReport) -> None:
        self._set_fetch_busy(False, topic_display_summary(self.topic.text()))
        NoticeDialog.info(
            self,
            "抓取结果",
            "已完成。",
            detail=report.to_user_text(),
        )
        if self.on_changed:
            self.on_changed({"fetch_done": True})

    def _on_fetch_failed(self, err: str) -> None:
        self._set_fetch_busy(False, "")
        NoticeDialog.info(self, "抓取失败", f"发生错误：{err}")

    def _persist_content_settings_only(self) -> None:
        self.ctx.settings.set("today_topic", self.topic.text().strip())
        self.ctx.settings.set("content_fetch_min_minutes", self.fetch_min.value())
        self.ctx.settings.set("content_fetch_max_minutes", self.fetch_max.value())
        self.ctx.settings.set("content_daily_limit", self.daily_limit.value())

    def _add_source(self, type_: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(f"添加 {type_} 来源")
        apply_readable_theme(dlg, self._theme)
        form = QFormLayout(dlg)
        name = QLineEdit()
        url = QLineEdit()
        cfg = QTextEdit()
        cfg.setMaximumHeight(80)
        if type_ == "rss":
            url.setPlaceholderText("https://example.com/feed.xml")
        elif type_ == "search":
            url.setText("bing_cn")
            url.setPlaceholderText("bing_cn（国内）| sogou | duckduckgo（需可访问）")
            cfg.setPlainText('{"provider": "bing_cn", "max_results": 10}')
        elif type_ == "web":
            cfg.setPlaceholderText('{"item_selector":"article h2 a"}')
        else:
            cfg.setPlaceholderText(
                '{"list_path":"items","title_key":"title","url_key":"url"}'
            )
        form.addRow("名称", name)
        form.addRow("URL / 提供方", url)
        form.addRow("解析配置（可选）", cfg)
        ok = QPushButton("添加")
        form.addRow(ok)

        def do() -> None:
            if not name.text().strip() or not url.text().strip():
                return
            self.ctx.content.add_source(
                name.text().strip(),
                type_,
                url.text().strip(),
                cfg.toPlainText().strip() or None,
            )
            self._reload_sources()
            dlg.accept()

        ok.clicked.connect(do)
        dlg.exec()

    def _del_source(self) -> None:
        sid = self._selected_source_id()
        if sid is None:
            return
        self.ctx.content.delete_source(sid)
        self._reload_sources()

    def _model_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.provider = QLineEdit(self.ctx.settings.get("llm_provider_name") or "")
        self.base_url = QLineEdit(self.ctx.settings.get("llm_base_url") or "")
        self.model = QLineEdit(self.ctx.settings.get("llm_model") or "")
        key = self.ctx.secrets.get_llm_api_key() or ""
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText(
            SecretStore.mask(key) if key else "保存在 Windows Credential Manager"
        )
        self.api_key_value = key
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setValue(int(self.ctx.settings.get("llm_timeout", 30)))
        self.test_llm_btn = QPushButton("测试连接")
        self.test_llm_btn.clicked.connect(self._test_llm)
        self.llm_status = QLabel("")
        self.llm_status.setObjectName("Muted")
        self.llm_status.setWordWrap(True)
        form.addRow("Provider", self.provider)
        form.addRow("Base URL", self.base_url)
        form.addRow("Model", self.model)
        form.addRow("API Key", self.api_key)
        form.addRow("Timeout", self.timeout)
        form.addRow(self.test_llm_btn)
        form.addRow(self.llm_status)
        tip = QLabel("测试在后台进行，不会卡住整个应用。API Key 不写入 SQLite。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        form.addRow(tip)
        return w

    def _test_llm(self) -> None:
        if self._llm_worker and self._llm_worker.isRunning():
            return
        key = self.api_key.text().strip() or self.api_key_value
        self.test_llm_btn.setEnabled(False)
        self.llm_status.setText("测试中…（后台请求，请稍候）")
        self._llm_worker = LlmTestWorker(
            self.base_url.text().strip(),
            key,
            self.model.text().strip(),
            float(self.timeout.value()),
        )
        self._llm_worker.finished.connect(self._on_llm_test_done)
        self._llm_worker.failed.connect(self._on_llm_test_fail)
        self._llm_worker.start()

    def _on_llm_test_done(self, result) -> None:
        self.test_llm_btn.setEnabled(True)
        self.llm_status.setText(
            f"{'成功' if result.ok else '失败'} · {result.message} · {result.latency_ms} ms"
        )

    def _on_llm_test_fail(self, err: str) -> None:
        self.test_llm_btn.setEnabled(True)
        self.llm_status.setText(f"失败 · {err}")

    def _mail_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        tip = QLabel(
            "通过 SMTP 直接发给自己（QQ/163 等请用「授权码」，不是登录密码）。"
            "导出向导里「发送邮件」依赖此配置，不会打开 Outlook。"
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        form.addRow(tip)
        self.mail_host = QLineEdit(self.ctx.settings.get("mail_smtp_host") or "")
        self.mail_host.setPlaceholderText("smtp.qq.com")
        self.mail_port = QSpinBox()
        self.mail_port.setRange(1, 65535)
        self.mail_port.setValue(int(self.ctx.settings.get("mail_smtp_port") or 465))
        self.mail_user = QLineEdit(self.ctx.settings.get("mail_smtp_user") or "")
        self.mail_to = QLineEdit(self.ctx.settings.get("mail_smtp_to") or "")
        self.mail_to.setPlaceholderText("默认可与发件账号相同")
        smtp_pwd = self.ctx.secrets.get_smtp_password() or ""
        self.mail_password = QLineEdit()
        self.mail_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.mail_password.setPlaceholderText(
            SecretStore.mask(smtp_pwd) if smtp_pwd else "授权码，存 Credential Manager"
        )
        self.mail_password_value = smtp_pwd
        self.mail_ssl = QCheckBox("使用 SSL（465 端口）")
        self.mail_ssl.setChecked(bool(self.ctx.settings.get("mail_smtp_use_ssl", True)))
        form.addRow("SMTP 主机", self.mail_host)
        form.addRow("端口", self.mail_port)
        form.addRow("发件邮箱", self.mail_user)
        form.addRow("SMTP 授权码", self.mail_password)
        form.addRow("默认收件人", self.mail_to)
        form.addRow(self.mail_ssl)
        self.test_mail_btn = QPushButton("试发邮件")
        self.test_mail_btn.clicked.connect(self._test_mail)
        self.mail_status = QLabel("")
        self.mail_status.setObjectName("Muted")
        self.mail_status.setWordWrap(True)
        form.addRow(self.test_mail_btn)
        form.addRow(self.mail_status)
        return w

    def _smtp_client_from_form(self) -> SmtpMailClient | None:
        host = self.mail_host.text().strip()
        user = self.mail_user.text().strip()
        pwd = self.mail_password.text().strip() or self.mail_password_value
        if not host or not user or not pwd:
            return None
        return SmtpMailClient(
            host,
            self.mail_port.value(),
            user,
            pwd,
            use_ssl=self.mail_ssl.isChecked(),
        )

    def _test_mail(self) -> None:
        if self._mail_test_worker and self._mail_test_worker.isRunning():
            return
        client = self._smtp_client_from_form()
        to = (
            self.mail_to.text().strip()
            or self.mail_user.text().strip()
        )
        if client is None:
            self.mail_status.setText("请先填写 SMTP 主机、发件邮箱与授权码。")
            return
        if not to:
            self.mail_status.setText("请填写默认收件人（可填自己的邮箱）。")
            return
        self.test_mail_btn.setEnabled(False)
        self.mail_status.setText("试发中…")
        self._mail_test_worker = MailTestWorker(client, to)
        self._mail_test_worker.finished.connect(self._on_mail_test_done)
        self._mail_test_worker.failed.connect(self._on_mail_test_fail)
        self._mail_test_worker.start()

    def _on_mail_test_done(self, result) -> None:
        self.test_mail_btn.setEnabled(True)
        self.mail_status.setText(
            f"{'成功' if result.ok else '失败'} · {result.message}"
        )

    def _on_mail_test_fail(self, err: str) -> None:
        self.test_mail_btn.setEnabled(True)
        self.mail_status.setText(f"失败 · {err}")

    def _work_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.root_list = QListWidget()
        self._reload_roots()
        layout.addWidget(self.root_list)
        row = QHBoxLayout()
        add = QPushButton("添加工作目录")
        add.clicked.connect(self._add_root)
        remove = QPushButton("移除")
        remove.clicked.connect(self._remove_root)
        row.addWidget(add)
        row.addWidget(remove)
        layout.addLayout(row)
        layout.addWidget(QLabel("忽略规则（每行一个）"))
        self.ignore = QTextEdit()
        patterns = self.ctx.settings.get("ignore_patterns") or []
        self.ignore.setPlainText("\n".join(patterns))
        layout.addWidget(self.ignore)
        form = QFormLayout()
        self.hash_mb = QSpinBox()
        self.hash_mb.setRange(1, 8192)
        max_bytes = int(self.ctx.settings.get("hash_max_bytes", 2 * 1024**3))
        self.hash_mb.setValue(max(1, max_bytes // (1024 * 1024)))
        self.debounce = QSpinBox()
        self.debounce.setRange(1, 60)
        self.debounce.setValue(int(self.ctx.settings.get("modify_debounce_seconds", 5)))
        form.addRow("自动哈希上限（MB）", self.hash_mb)
        form.addRow("MODIFY 去抖（秒）", self.debounce)
        layout.addLayout(form)
        return w

    def _reload_roots(self) -> None:
        self.root_list.clear()
        self._roots = self.ctx.worklog.list_roots()
        for r in self._roots:
            flag = "✓" if r.enabled else "✗"
            self.root_list.addItem(f"[{flag}] {r.path}")

    def _add_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择工作目录")
        if path:
            self.ctx.worklog.add_root(path)
            self._reload_roots()
            if self.on_changed:
                self.on_changed({"reload_watch": True})

    def _remove_root(self) -> None:
        idx = self.root_list.currentRow()
        if idx < 0:
            return
        self.ctx.worklog.delete_root(self._roots[idx].id)
        self._reload_roots()
        if self.on_changed:
            self.on_changed({"reload_watch": True})

    def _clear_stats(self) -> None:
        if not NoticeDialog.confirm(
            self, "确认清空", "将清空提醒事件、内容缓存、会话与导出日志，是否继续？"
        ):
            return
        self.ctx.reminders.clear_events()
        self.ctx.content.clear_all()
        self.ctx.sessions.clear()
        self.ctx.exports.clear()
        NoticeDialog.info(self, "完成", "本地统计已清空。")

    def _save(self) -> None:
        old_theme = str(self.ctx.settings.get("ui_theme") or "light")
        new_theme = str(self.ui_theme.currentData() or "light")
        self.ctx.settings.set("ui_theme", new_theme)
        self.ctx.settings.set("autostart", self.autostart.isChecked())
        self.ctx.settings.set("notification_fade_seconds", self.fade.value())
        self.ctx.settings.set("defer_when_fullscreen", self.fullscreen.isChecked())
        self.ctx.settings.set("data_retention_days", self.retention.value())
        self.ctx.settings.set("today_topic", self.topic.text().strip())
        self.ctx.settings.set("content_fetch_min_minutes", self.fetch_min.value())
        self.ctx.settings.set("content_fetch_max_minutes", self.fetch_max.value())
        self.ctx.settings.set("content_daily_limit", self.daily_limit.value())
        self.ctx.settings.set("llm_provider_name", self.provider.text().strip())
        self.ctx.settings.set("llm_base_url", self.base_url.text().strip())
        self.ctx.settings.set("llm_model", self.model.text().strip())
        self.ctx.settings.set("llm_timeout", self.timeout.value())
        key = self.api_key.text().strip()
        if key:
            self.ctx.secrets.set_llm_api_key(key)
            self.api_key_value = key
            self.api_key.clear()
            self.api_key.setPlaceholderText(SecretStore.mask(key))
        self.ctx.settings.set("mail_smtp_host", self.mail_host.text().strip())
        self.ctx.settings.set("mail_smtp_port", self.mail_port.value())
        self.ctx.settings.set("mail_smtp_user", self.mail_user.text().strip())
        self.ctx.settings.set("mail_smtp_to", self.mail_to.text().strip())
        self.ctx.settings.set("mail_smtp_use_ssl", self.mail_ssl.isChecked())
        mail_pwd = self.mail_password.text().strip()
        if mail_pwd:
            self.ctx.secrets.set_smtp_password(mail_pwd)
            self.mail_password_value = mail_pwd
            self.mail_password.clear()
            self.mail_password.setPlaceholderText(SecretStore.mask(mail_pwd))
        patterns = [ln.strip() for ln in self.ignore.toPlainText().splitlines() if ln.strip()]
        self.ctx.settings.set("ignore_patterns", patterns)
        self.ctx.settings.set("hash_max_bytes", self.hash_mb.value() * 1024 * 1024)
        self.ctx.settings.set("modify_debounce_seconds", self.debounce.value())
        self.ctx.refresh_path_policy()
        from fishmate.services.autostart import set_autostart

        set_autostart(self.autostart.isChecked())
        if new_theme != old_theme:
            self._theme = new_theme
            apply_readable_theme(self, new_theme)
        if self.on_changed:
            payload: dict = {"saved": True}
            if new_theme != old_theme:
                payload["theme_changed"] = True
            self.on_changed(payload)
        NoticeDialog.saved(self)
