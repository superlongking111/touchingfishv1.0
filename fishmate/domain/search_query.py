"""Build search queries and post-filter results for topic relevance."""

from __future__ import annotations

from datetime import datetime

from fishmate.domain.content import Candidate
from fishmate.domain.topic import parse_topic_tokens


def build_search_query(topic_raw: str, cfg: dict | None = None) -> str:
    cfg = cfg or {}
    tokens = parse_topic_tokens(topic_raw)
    if not tokens:
        return topic_raw.strip()
    # 整词检索，避免「伪娘」被搜成「伪」的释义
    core = " ".join(tokens[:3])
    suffix = str(cfg.get("query_suffix", " 新闻"))
    year = datetime.now().year
    if cfg.get("append_current_year", True):
        return f"{core} {year} 最新{suffix}"
    return f"{core}{suffix}"


def search_result_matches_topic(
    title: str, summary: str, topic_raw: str, tokens: list[str] | None = None
) -> bool:
    text = f"{title} {summary}"
    raw = topic_raw.strip()
    if raw and raw in text:
        return True
    for t in tokens or parse_topic_tokens(topic_raw):
        if len(t) >= 2 and t in text:
            return True
    return False


def filter_candidates_by_topic(
    items: list[Candidate], topic_raw: str
) -> list[Candidate]:
    tokens = parse_topic_tokens(topic_raw)
    return [
        c
        for c in items
        if search_result_matches_topic(c.title, c.summary or "", topic_raw, tokens)
    ]
