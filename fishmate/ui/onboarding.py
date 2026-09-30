"""First-run onboarding wizard — minimal, high-contrast."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from fishmate.bootstrap import resource_path
from fishmate.services.autostart import set_autostart
from fishmate.domain.topic import TOPIC_SEPARATOR_HINT
from fishmate.ui.style import apply_readable_theme

if TYPE_CHECKING:
    from fishmate.app_context import AppContext


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("FieldLabel")
    return lbl


class OnboardingDialog(QDialog):
    def __init__(self, ctx: "AppContext", parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("欢迎使用摸鱼助手")
        apply_readable_theme(self, str(ctx.settings.get("ui_theme") or "light"))
        self.setMinimumSize(480, 560)
        self.resize(520, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        header = QHBoxLayout()
        logo_path = resource_path("resources", "icons", "app_64.png")
        if logo_path.is_file():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(logo_path)))
            logo.setFixedSize(56, 56)
            header.addWidget(logo)
        brand = QLabel("摸鱼助手")
        brand.setObjectName("Brand")
        header.addWidget(brand)
        header.addStretch()
        root.addLayout(header)

        desc = QLabel(
            "Windows 办公轻量伴侣 · 仅小摸鱼 / 摸大鱼两种状态\n"
            "本地优先，工作文件正文默认不发给模型"
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        root.addWidget(desc)
        root.addSpacing(16)

        # Scrollable form body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(4)

        self.autostart = QCheckBox("开机自动启动（默认关闭）")
        form.addWidget(self.autostart)
        form.addSpacing(10)

        form.addWidget(_field_label("今日话题（可选）"))
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("例如：AI Agent，大模型 / 自动化")
        form.addWidget(self.topic)
        topic_tip = QLabel(TOPIC_SEPARATOR_HINT)
        topic_tip.setObjectName("Muted")
        topic_tip.setWordWrap(True)
        form.addWidget(topic_tip)

        form.addWidget(_field_label("模型 Base URL（可选）"))
        self.base_url = QLineEdit("https://api.openai.com/v1")
        form.addWidget(self.base_url)

        form.addWidget(_field_label("Model"))
        self.model = QLineEdit("gpt-4o-mini")
        form.addWidget(self.model)

        form.addWidget(_field_label("API Key"))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("保存在系统凭据管理器，不写入数据库")
        form.addWidget(self.api_key)

        form.addWidget(_field_label("授权工作目录（可选）"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.work_dir = QLineEdit()
        self.work_dir.setPlaceholderText("选择后才会监听文件变化")
        pick = QPushButton("选择目录")
        pick.setObjectName("Ghost")
        pick.setFixedWidth(96)
        pick.clicked.connect(self._pick)
        dir_row.addWidget(self.work_dir, stretch=1)
        dir_row.addWidget(pick)
        form.addLayout(dir_row)

        form.addSpacing(12)
        tip = QLabel("通知出现在右下角。关闭窗口不会退出，请从系统托盘退出。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        form.addWidget(tip)
        form.addStretch()

        scroll.setWidget(body)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.viewport().setAutoFillBackground(True)
        scroll.viewport().setStyleSheet("background-color: #ffffff;")
        body.setAutoFillBackground(True)
        root.addWidget(scroll, stretch=1)
        root.addSpacing(16)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        skip = QPushButton("全部跳过")
        skip.setObjectName("Ghost")
        skip.clicked.connect(self._skip)
        go = QPushButton("开始小摸鱼")
        go.setObjectName("Primary")
        go.setMinimumWidth(140)
        go.clicked.connect(self._finish)
        actions.addWidget(skip)
        actions.addStretch()
        actions.addWidget(go)
        root.addLayout(actions)

    def _pick(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择工作目录")
        if path:
            self.work_dir.setText(path)

    def _skip(self) -> None:
        self.ctx.settings.set("onboarding_done", True)
        self.accept()

    def _finish(self) -> None:
        self.ctx.settings.set("autostart", self.autostart.isChecked())
        set_autostart(self.autostart.isChecked())
        if self.topic.text().strip():
            self.ctx.settings.set("today_topic", self.topic.text().strip())
        if self.base_url.text().strip():
            self.ctx.settings.set("llm_base_url", self.base_url.text().strip())
        if self.model.text().strip():
            self.ctx.settings.set("llm_model", self.model.text().strip())
        if self.api_key.text().strip():
            self.ctx.secrets.set_llm_api_key(self.api_key.text().strip())
        if self.work_dir.text().strip():
            self.ctx.worklog.add_root(self.work_dir.text().strip())
        self.ctx.settings.set("onboarding_done", True)
        self.accept()
