from datetime import datetime, timedelta

from fishmate.domain.content import Candidate
from fishmate.domain.search_recency import apply_search_recency, parse_date_from_text


def test_parse_relative_and_absolute():
    now = datetime(2026, 9, 29, 12, 0, 0)
    assert parse_date_from_text("3小时前", now) == now - timedelta(hours=3)
    assert parse_date_from_text("2026-08-05 报道", now).month == 8


def test_apply_recency_keeps_undated():
    now = datetime(2026, 9, 29)
    items = [Candidate("无日期", "http://a", "摘要里没有时间", published_at=None)]
    out = apply_search_recency(items, {"max_recency_days": 45}, 5, now=now)
    assert len(out) == 1
    assert out[0].title == "无日期"


def test_apply_recency_drops_old():
    now = datetime(2026, 9, 29)
    items = [
        Candidate("新", "http://a", "2026-09-20 发布", published_at=None),
        Candidate("旧", "http://b", "2017-07-08 发布", published_at=None),
    ]
    out = apply_search_recency(items, {"max_recency_days": 45}, 5, now=now)
    assert len(out) == 1
    assert out[0].title == "新"
