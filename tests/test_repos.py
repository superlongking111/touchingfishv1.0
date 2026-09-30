from pathlib import Path

from fishmate.repositories.db import Database
from fishmate.repositories.settings_repo import SettingsRepo
from fishmate.repositories.reminder_repo import ReminderRepo
from fishmate.repositories.content_repo import ContentRepo, DEFAULT_CONTENT_SOURCES
from fishmate.repositories.worklog_repo import WorklogRepo
from fishmate.domain.content import canonical_hash


def test_db_migrate_and_settings(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    settings = SettingsRepo(db)
    settings.ensure_defaults()
    assert settings.get("notification_fade_seconds") == 10
    settings.set("today_topic", "AI")
    assert settings.get("today_topic") == "AI"
    db.close()


def test_reminders_seed(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    repo = ReminderRepo(db)
    repo.seed_defaults()
    repo.seed_defaults()  # idempotent
    items = repo.list_all()
    assert len(items) == 4
    assert {i.type for i in items} >= {"water", "walk", "rest", "toilet"}
    db.close()


def test_default_sources_are_leisure_oriented():
    names = [n for n, *_ in DEFAULT_CONTENT_SOURCES]
    assert any("主题资讯搜索" in n for n in names)
    assert any("Bilibili" in n for n in names)
    assert any("新浪" in n for n in names)
    assert any("ACG17" in n for n in names)
    assert not any("OpenAI" in n for n in names)
    assert len(names) == 5


def test_delete_source_removes_linked_items(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    repo = ContentRepo(db)
    sid = repo.add_source("旧源", "rss", "https://legacy.example/rss")
    h = canonical_hash("https://legacy.example/1", "x")
    repo.insert_item(h, sid, "x", "https://legacy.example/1", None, "s", status="ready")
    repo.delete_source(sid)
    assert repo.db.query_one("SELECT 1 FROM content_sources WHERE id=?", (sid,)) is None
    assert repo.db.query_one("SELECT 1 FROM content_items WHERE source_id=?", (sid,)) is None
    db.close()


def test_content_dedupe(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    repo = ContentRepo(db)
    sid = repo.add_source("HN", "rss", "https://example.com/rss")
    h = canonical_hash("https://example.com/a", "T")
    assert repo.insert_item(h, sid, "T", "https://example.com/a", None, "s")
    assert repo.insert_item(h, sid, "T", "https://example.com/a", None, "s") is None
    db.close()


def test_worklog_debounce_update(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    repo = WorklogRepo(db)
    rid = repo.add_root(str(tmp_path))
    eid = repo.insert_event(rid, "MODIFY", str(tmp_path / "a.py"), size=1)
    recent = repo.recent_modify(str(tmp_path / "a.py"), 10)
    assert recent is not None
    assert recent.id == eid
    db.close()
