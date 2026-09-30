"""One-off preview: show ContentFishToast on screen (run from project root)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from fishmate.bootstrap import db_path
from fishmate.repositories import Database, SettingsRepo
from fishmate.repositories.content_repo import ContentItem
from fishmate.ui.app_icon import app_icon
from fishmate.ui.style import apply_app_theme
from fishmate.ui.widgets.content_toast import ContentFishToast


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("摸鱼助手 · 弹窗预览")
    ic = app_icon()
    if not ic.isNull():
        app.setWindowIcon(ic)

    db = Database(db_path())
    settings = SettingsRepo(db)
    settings.ensure_defaults()
    theme = str(settings.get("ui_theme") or "light")
    apply_app_theme(app, theme)

    item = ContentItem(
        id=-1,
        canonical_hash="preview",
        source_id=None,
        title="【预览】摸鱼助手 · 内容弹窗",
        url="https://www.bilibili.com",
        published_at=datetime.now().strftime("%Y-%m-%d"),
        summary="这是一条演示摘要：右下角 Toast、链接标题、看看别的 / 摸大鱼 / 关闭。",
        llm_score=9.0,
        llm_reason="你在预览界面效果",
        short_summary="鼠标悬停会暂停淡出。主题可在 设置→常规→界面主题 里切换后重新运行本脚本。",
        status="pushed",
        created_at=datetime.now().isoformat(),
    )

    content = SimpleNamespace(
        pick_random_portal_ready=lambda _seen: None,
        set_status=lambda *_a, **_k: None,
    )
    ctx = SimpleNamespace(
        settings=settings,
        content=content,
        db=SimpleNamespace(query_one=lambda *_a, **_k: None),
    )

    toast = ContentFishToast(
        ctx,
        item,
        fade_seconds=int(settings.get("notification_fade_seconds") or 12),
        on_open_big=lambda: print("预览：点击了「摸大鱼」"),
    )
    toast.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
