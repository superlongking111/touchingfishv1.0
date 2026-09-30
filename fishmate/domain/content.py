"""Content discovery domain: hashing, dedupe, keyword fallback."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


# 小摸鱼内容弹窗：标题/正文长度上限
TOAST_TITLE_MAX = 72
TOAST_BODY_MAX = 96
LLM_SUMMARY_TARGET = "40-80 字"


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "fbclid",
    "gclid",
}


@dataclass
class Candidate:
    title: str
    url: str
    summary: str
    published_at: str | None = None
    source_id: int | None = None


@dataclass
class RankedItem:
    candidate: Candidate
    relevance: float
    interest: float
    reason: str
    short_summary: str


@dataclass
class SearchTopicDigest:
    """One-line toast copy synthesized from latest search hits."""

    title: str
    summary: str
    pick_i: int
    reason: str = ""


SEARCH_DIGEST_INPUT = 8


def canonicalize_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        scheme = (p.scheme or "https").lower()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path.rstrip("/") or "/"
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        query = urlencode(sorted(query_pairs))
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:  # noqa: BLE001
        return url.strip()


def canonical_hash(url: str, title: str = "") -> str:
    base = canonicalize_url(url)
    raw = f"{base}|{title.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def title_similar(a: str, b: str, threshold: float = 0.92) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio() >= threshold


def blurb_is_weak(title: str, summary: str | None, short_summary: str | None) -> bool:
    """True when display text adds no information beyond the headline."""
    t = (title or "").strip()
    if not t:
        return True
    for raw in (short_summary, summary):
        if not raw:
            continue
        s = raw.strip()
        if len(s) < 16:
            return True
        if title_similar(s, t):
            return True
        if t in s and len(s) <= len(t) + 6:
            return True
    return not (short_summary or summary)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def rss_body_excerpt(
    body: str | None,
    title: str,
    *,
    max_len: int = 20,
) -> str:
    """
    截取抓取到的正文/摘要片段（不用模型）。
    与标题相同或为空则返回空字符串，避免列表里标题写两遍。
    """
    s = _collapse_ws(body or "")
    t = _collapse_ws(title)
    if not s:
        return ""
    if title_similar(s, t):
        return ""
    if t and s.startswith(t):
        rest = s[len(t) :].lstrip(" ：:—-|·")
        s = rest or s
        if not s or title_similar(s, t):
            return ""
    if max_len <= 0:
        return s
    return _ellipsis_trim(s, max_len)


def is_search_digest_item(item: "ContentItemLike") -> bool:
    """仅「主题搜索 → 模型一句话摘要」走 LLM 文案；门户/RSS 不用."""
    reason = (getattr(item, "llm_reason", None) or "").strip()
    return "搜索" in reason and "摘要" in reason


def fallback_portal_blurb(candidate: Candidate) -> str:
    """门户仅有标题时的本地提示（不调用模型）。"""
    ex = rss_body_excerpt(candidate.summary, candidate.title, max_len=96)
    if ex:
        return ex
    return "暂无正文摘录，请点击「打开原文」阅读。"


def keyword_score(topic: str, title: str, summary: str) -> float:
    from fishmate.domain.topic import parse_topic_tokens

    tokens = [t.lower() for t in parse_topic_tokens(topic)]
    if not tokens:
        return 0.3
    text = f"{title} {summary}".lower()
    hits = sum(1 for t in tokens if t in text)
    if hits == 0:
        return 0.0
    return min(1.0, 0.35 + 0.65 * (hits / len(tokens)))


def rank_with_keywords(
    topic: str,
    items: list[Candidate],
    threshold: float = 0.55,
    *,
    include_below: bool = False,
) -> list[RankedItem]:
    """Score all items; by default only return those >= threshold."""
    scored: list[RankedItem] = []
    for c in items:
        score = keyword_score(topic, c.title, c.summary)
        if score >= threshold or include_below:
            scored.append(
                RankedItem(
                    candidate=c,
                    relevance=score,
                    interest=score * 0.9,
                    reason="关键词相关（模型不可用时的降级筛选）",
                    short_summary=(c.summary or c.title)[:160],
                )
            )
    scored.sort(key=lambda x: x.relevance, reverse=True)
    return scored


def _ellipsis_trim(text: str, max_len: int) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def fallback_search_digest(topic: str, hits: list[Candidate]) -> SearchTopicDigest:
    """When LLM is unavailable: link newest hit, body from its snippet."""
    topic = topic.strip() or "话题"
    if not hits:
        return SearchTopicDigest(title=f"「{topic[:12]}」", summary="", pick_i=0)
    c = hits[0]
    body = (c.summary or c.title or "").strip()
    return SearchTopicDigest(
        title=f"「{topic[:14]}」最新",
        summary=body[:96],
        pick_i=0,
        reason="无模型，取最新一条",
    )


def search_digest_hash(topic: str, day: str | None = None) -> str:
    from datetime import datetime

    day = day or datetime.now().strftime("%Y-%m-%d")
    raw = f"search-topic-digest|{topic.strip().lower()}|{day}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def content_display_blurb(item: "ContentItemLike") -> tuple[str, str]:
    """
    弹窗：标题 + 正文。
    仅搜索话题摘要条目使用模型 short_summary；其余用 RSS/摘要原文截取。
    """
    title = _ellipsis_trim(item.title, TOAST_TITLE_MAX)
    raw_summary = getattr(item, "summary", None)
    if is_search_digest_item(item):
        short = (item.short_summary or "").strip()
        if short and not blurb_is_weak(item.title, raw_summary, short):
            body = _ellipsis_trim(short, TOAST_BODY_MAX)
        else:
            body = rss_body_excerpt(raw_summary, item.title, max_len=TOAST_BODY_MAX)
    else:
        body = rss_body_excerpt(raw_summary, item.title, max_len=TOAST_BODY_MAX)
        if not body:
            body = _ellipsis_trim(
                fallback_portal_blurb(
                    Candidate(title=item.title, url="", summary=raw_summary or "")
                ),
                TOAST_BODY_MAX,
            )
    return title, body


def content_detail_text(item: "ContentItemLike") -> str:
    """详情框：搜索摘要用模型句；门户/RSS 展示抓取正文（不扩写）。"""
    raw_summary = getattr(item, "summary", None)
    if is_search_digest_item(item):
        short = (item.short_summary or "").strip()
        if short and not blurb_is_weak(item.title, raw_summary, short):
            return short
    ex = rss_body_excerpt(raw_summary, item.title, max_len=0)
    if ex:
        return ex[:1200]
    return fallback_portal_blurb(
        Candidate(title=item.title, url=getattr(item, "url", "") or "", summary=raw_summary or "")
    )


def content_list_preview(item: "ContentItemLike", *, max_len: int = 20) -> str:
    """内容库列表第二行：正文前若干字，不与标题重复。"""
    return rss_body_excerpt(getattr(item, "summary", None), item.title, max_len=max_len)


class ContentItemLike(Protocol):
    title: str
    summary: str | None
    short_summary: str | None


def count_keyword_hits(topic: str, items: list[Candidate], threshold: float = 0.55) -> int:
    return sum(
        1
        for c in items
        if keyword_score(topic, c.title, c.summary) >= threshold
    )
