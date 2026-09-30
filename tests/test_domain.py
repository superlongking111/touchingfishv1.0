import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fishmate.domain.content import (
    TOAST_BODY_MAX,
    blurb_is_weak,
    canonicalize_url,
    canonical_hash,
    content_display_blurb,
    content_detail_text,
    content_list_preview,
    fallback_portal_blurb,
    rss_body_excerpt,
    keyword_score,
    rank_with_keywords,
    Candidate,
)
from types import SimpleNamespace
from fishmate.domain.reminders import ReminderPlanner
from fishmate.domain.worklog import aggregate_events, events_to_llm_payload
from fishmate.repositories.reminder_repo import Reminder
from fishmate.repositories.worklog_repo import FileEvent
from fishmate.security.path_policy import PathPolicy
from fishmate.services.exporter import ExportService
from fishmate.services.hash_worker import HashWorker


def test_canonicalize_strips_tracking():
    u = canonicalize_url("https://WWW.Example.com/a/b/?utm_source=x&id=1")
    assert u == "https://example.com/a/b?id=1"


def test_canonical_hash_stable():
    a = canonical_hash("https://example.com/x", "Hello")
    b = canonical_hash("https://example.com/x/", "Hello")
    assert a == b


def test_blurb_is_weak_when_same_as_title():
    assert blurb_is_weak("宫廷糕点 泼天流量", "宫廷糕点 泼天流量", "宫廷糕点 泼天流量")
    assert not blurb_is_weak(
        "OpenAI 发布新模型",
        None,
        "OpenAI 在春季发布会上公布了更小、更便宜的推理模型，面向企业 API。",
    )


def test_rss_excerpt_skips_duplicate_title():
    assert rss_body_excerpt("刚开始遇见都是美好的", "刚开始遇见都是美好的", max_len=20) == ""
    ex = rss_body_excerpt(
        "水谷隼：中国男兵实力整体下滑，教练组正在调整阵容。",
        "水谷隼：中国男兵实力整体下滑",
        max_len=20,
    )
    assert ex and "教练" in ex


def test_content_list_preview_twenty_chars():
    item = SimpleNamespace(
        title="标题",
        summary="这是正文开头后面还有很多字需要被截断",
    )
    prev = content_list_preview(item, max_len=20)
    assert len(prev) <= 21
    assert prev.startswith("这是正文")


def test_fallback_portal_blurb_not_empty_title_only():
    text = fallback_portal_blurb(
        Candidate("宫廷糕点 泼天流量", "https://x", "宫廷糕点 泼天流量")
    )
    assert "打开原文" in text


def test_content_detail_text_uses_fallback_for_weak():
    item = SimpleNamespace(
        title="宫廷糕点 泼天流量",
        summary="宫廷糕点 泼天流量",
        short_summary="宫廷糕点 泼天流量",
        url="https://example.com",
    )
    body = content_detail_text(item)
    assert body != item.title
    assert "打开原文" in body


def test_content_display_blurb_prefers_llm_summary():
    item = SimpleNamespace(
        title="Very long title " * 10,
        summary="rss summary " * 20,
        short_summary="模型写的短摘要：概括事件背景、主体动作与可能影响，供桌面弹窗阅读。",
        llm_reason="搜索一句话摘要",
    )
    title, body = content_display_blurb(item)
    assert body.startswith("模型写的短摘要")
    assert len(title) <= 72 + 1


def test_content_display_blurb_fallback_truncates():
    item = SimpleNamespace(
        title="T",
        summary="x" * 200,
        short_summary=None,
    )
    _, body = content_display_blurb(item)
    assert len(body) <= TOAST_BODY_MAX + 1
    assert body.endswith("…")


def test_keyword_rank():
    items = [
        Candidate("AI Agent roadmap", "https://a.com/1", "agents everywhere"),
        Candidate("Cooking pasta", "https://a.com/2", "tomato sauce"),
    ]
    ranked = rank_with_keywords("AI Agent", items, threshold=0.4)
    assert ranked
    assert ranked[0].candidate.title.startswith("AI")


def test_reminder_interval_and_fixed():
    planner = ReminderPlanner()
    r = Reminder(
        id=1,
        type="water",
        name="喝水",
        enabled=True,
        schedule_type="interval",
        interval_minutes=45,
        fixed_times=[],
        jitter_minutes=0,
        active_window={"start": "00:00", "end": "23:59"},
        message="喝水",
    )
    now = datetime(2026, 9, 29, 10, 0, 0)
    nxt = planner.schedule_next(r, now)
    assert nxt == now + timedelta(minutes=45)

    r2 = Reminder(
        id=2,
        type="toilet",
        name="厕所",
        enabled=True,
        schedule_type="fixed",
        interval_minutes=None,
        fixed_times=["10:30", "15:30"],
        jitter_minutes=0,
        active_window={"start": "00:00", "end": "23:59"},
        message="到点了",
    )
    nxt2 = planner.schedule_next(r2, now)
    assert nxt2.hour == 10 and nxt2.minute == 30


def test_reminder_reschedule_after_interval_change():
    planner = ReminderPlanner()
    r = Reminder(
        id=1,
        type="water",
        name="喝水",
        enabled=True,
        schedule_type="interval",
        interval_minutes=45,
        fixed_times=[],
        jitter_minutes=0,
        active_window={"start": "00:00", "end": "23:59"},
        message="喝水",
    )
    t0 = datetime(2026, 9, 29, 10, 0, 0)
    planner.schedule_next(r, t0)
    r.interval_minutes = 1
    planner.reschedule(r, t0)
    assert planner._next_fire[1] == t0 + timedelta(minutes=1)


def test_reminder_outside_window_advances_without_popup():
    planner = ReminderPlanner()
    r = Reminder(
        id=1,
        type="water",
        name="喝水",
        enabled=True,
        schedule_type="interval",
        interval_minutes=1,
        fixed_times=[],
        jitter_minutes=0,
        active_window={"start": "09:00", "end": "10:00"},
        message="x",
    )
    now = datetime(2026, 9, 29, 20, 0, 0)
    planner._next_fire[1] = now - timedelta(minutes=1)
    due = planner.due_now([r], now=now)
    assert due == []
    assert planner._next_fire[1] > now


def test_reminder_snooze_blocks_refire_until_elapsed():
    planner = ReminderPlanner()
    r = Reminder(
        id=1,
        type="water",
        name="喝水",
        enabled=True,
        schedule_type="interval",
        interval_minutes=1,
        fixed_times=[],
        jitter_minutes=0,
        active_window={"start": "00:00", "end": "23:59"},
        message="x",
    )
    t0 = datetime(2026, 9, 29, 10, 0, 0)
    planner._next_fire[1] = t0
    due = planner.due_now([r], now=t0)
    assert len(due) == 1
    planner.acknowledge(r, "snooze", snooze_minutes=10, from_time=t0)
    t2 = t0 + timedelta(minutes=2)
    assert planner.due_now([r], now=t2) == []
    t10 = t0 + timedelta(minutes=10)
    due_later = planner.due_now([r], now=t10)
    assert len(due_later) == 1


def test_reminder_waits_for_acknowledge_before_reschedule():
    planner = ReminderPlanner()
    r = Reminder(
        id=1,
        type="water",
        name="喝水",
        enabled=True,
        schedule_type="interval",
        interval_minutes=1,
        fixed_times=[],
        jitter_minutes=0,
        active_window={"start": "00:00", "end": "23:59"},
        message="x",
    )
    t0 = datetime(2026, 9, 29, 10, 0, 0)
    planner._next_fire[1] = t0
    assert len(planner.due_now([r], now=t0)) == 1
    t1 = t0 + timedelta(minutes=1)
    assert planner.due_now([r], now=t1) == []
    planner.acknowledge(r, "primary", from_time=t1)
    assert planner._next_fire[1] == t1 + timedelta(minutes=1)


def test_ensure_scheduled_noop_while_frozen():
    planner = ReminderPlanner()
    r = Reminder(
        id=1,
        type="water",
        name="喝水",
        enabled=True,
        schedule_type="interval",
        interval_minutes=45,
        fixed_times=[],
        jitter_minutes=0,
        active_window={"start": "00:00", "end": "23:59"},
        message="x",
    )
    t0 = datetime(2026, 9, 29, 10, 0, 0)
    planner.freeze_timers(t0)
    planner.ensure_scheduled([r])
    assert 1 not in planner._next_fire


def test_reminder_freeze_no_popup_and_preserves_remaining():
    planner = ReminderPlanner()
    r = Reminder(
        id=1,
        type="water",
        name="喝水",
        enabled=True,
        schedule_type="interval",
        interval_minutes=1,
        fixed_times=[],
        jitter_minutes=0,
        active_window={"start": "00:00", "end": "23:59"},
        message="x",
    )
    t0 = datetime(2026, 9, 29, 10, 0, 0)
    planner._next_fire[1] = t0 + timedelta(minutes=10)
    planner.freeze_timers(t0)
    assert planner.due_now([r], now=t0 + timedelta(minutes=30), in_big_fish=True) == []
    planner.resume_timers_after_freeze(t0 + timedelta(minutes=30))
    assert planner._next_fire[1] == t0 + timedelta(minutes=40)


def test_reminder_due_now_returns_at_most_one():
    planner = ReminderPlanner()
    rs = [
        Reminder(
            id=i,
            type="water",
            name=f"r{i}",
            enabled=True,
            schedule_type="interval",
            interval_minutes=1,
            fixed_times=[],
            jitter_minutes=0,
            active_window={"start": "00:00", "end": "23:59"},
            message="x",
        )
        for i in (1, 2)
    ]
    t0 = datetime(2026, 9, 29, 10, 0, 0)
    planner._next_fire[1] = t0
    planner._next_fire[2] = t0
    due = planner.due_now(rs, now=t0)
    assert len(due) == 1


def test_aggregate_and_payload():
    events = [
        FileEvent(1, 1, "2026-09-29T09:21:00", "MODIFY", "D:/w/src/login.py", None, 1, None, None),
        FileEvent(2, 1, "2026-09-29T09:22:00", "MODIFY", "D:/w/src/login.py", None, 1, None, None),
        FileEvent(3, 1, "2026-09-29T10:43:00", "CREATE", "D:/w/docs/PRD.docx", None, 1, None, None),
    ]
    agg = aggregate_events(events)
    assert len(agg) == 2
    payload = events_to_llm_payload(events, "notes", "2026-09-29")
    assert payload["date"] == "2026-09-29"
    assert len(payload["events"]) == 3


def test_path_policy_ignore_and_export(tmp_path: Path):
    policy = PathPolicy(["*.tmp", "node_modules", "~$*"])
    assert policy.should_ignore(tmp_path / "a.tmp")
    assert policy.should_ignore(tmp_path / "node_modules" / "x.js")
    f = tmp_path / "report.txt"
    f.write_text("hello", encoding="utf-8")
    checked = policy.validate_export_files([f])
    assert checked[0][1] is None


def test_export_zip_manifest_verify(tmp_path: Path, monkeypatch):
    from fishmate import bootstrap

    monkeypatch.setattr(bootstrap, "export_dir", lambda: tmp_path)
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha", encoding="utf-8")
    b.write_text("beta", encoding="utf-8")
    svc = ExportService(PathPolicy())
    result = svc.build_zip([a, b], include_worklog=True, worklog_data=[{"x": 1}])
    assert result.ok
    assert Path(result.zip_path).exists()
    assert ExportService.verify_zip(result.zip_path)
    # sha of zip present
    assert len(result.zip_sha256) == 64


def test_hash_worker_sync(tmp_path: Path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"12345")
    assert HashWorker.hash_file_sync(f) == HashWorker.hash_file_sync(f)
