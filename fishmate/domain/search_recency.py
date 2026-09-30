"""Parse dates from search snippets and prefer recent news."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fishmate.domain.content import Candidate

_DATE_RE = re.compile(
    r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})"
)
_MINUTES_AGO = re.compile(r"(\d+)\s*分钟前")
_HOURS_AGO = re.compile(r"(\d+)\s*小时前")
_DAYS_AGO = re.compile(r"(\d+)\s*天前")


def parse_date_from_text(text: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    if "今天" in text or "刚刚" in text:
        return now
    if "昨天" in text:
        return now - timedelta(days=1)
    m = _MINUTES_AGO.search(text)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = _HOURS_AGO.search(text)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = _DAYS_AGO.search(text)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = _DATE_RE.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def apply_search_recency(
    items: list[Candidate],
    cfg: dict | None,
    limit: int,
    *,
    now: datetime | None = None,
) -> list[Candidate]:
    """Drop stale hits, sort newest first; annotate published_at when parsed."""
    cfg = cfg or {}
    max_days = int(cfg.get("max_recency_days", 45))
    require_date = bool(cfg.get("require_recency_date", False))
    now = now or datetime.now()
    scored: list[tuple[datetime, Candidate]] = []
    for c in items:
        blob = f"{c.title} {c.summary or ''}"
        dt = parse_date_from_text(blob, now)
        if dt is None:
            if require_date:
                continue
            # 搜狗等摘要常无日期：保留条目，按「当前」参与排序，不按过期丢弃
            dt = now
        age = (now - dt).days
        if age > max_days:
            continue
        if not c.published_at:
            c.published_at = dt.astimezone().isoformat(timespec="seconds")
        scored.append((dt, c))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:limit]]
