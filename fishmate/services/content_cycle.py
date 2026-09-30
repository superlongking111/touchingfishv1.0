"""Content fetch → dedupe → rank pipeline (shared by scheduler & settings)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from fishmate.domain.content import (
    SEARCH_DIGEST_INPUT,
    Candidate,
    SearchTopicDigest,
    canonical_hash,
    count_keyword_hits,
    fallback_search_digest,
    keyword_score,
    search_digest_hash,
    title_similar,
)
from fishmate.domain.search_recency import apply_search_recency
from fishmate.domain.sources import is_search_source
from fishmate.domain.topic import parse_topic_tokens
from fishmate.services.content_fetcher import ContentFetcher
from fishmate.services.llm_client import LLMClient

if True:
    from fishmate.app_context import AppContext

logger = logging.getLogger("fishmate.content_cycle")

@dataclass
class SourceFetchLine:
    name: str
    type: str
    ok: bool
    count: int = 0
    error: str | None = None
    sample_titles: list[str] = field(default_factory=list)


@dataclass
class ContentCycleReport:
    topic_tokens: list[str]
    topic_raw: str = ""
    lines: list[SourceFetchLine] = field(default_factory=list)
    fetched_total: int = 0
    new_candidates: int = 0
    ready_after: int = 0
    skipped_reason: str | None = None
    used_llm: bool = False
    llm_batches: int = 0
    llm_error: str | None = None
    keyword_hits: int = 0
    ranked_ready: int = 0
    ranked_rejected: int = 0
    search_digest_ready: int = 0
    portal_browse_ready: int = 0
    push_blocked_by_limit: bool = False
    llm_payload_preview: str | None = None
    topic_literal_examples: list[str] = field(default_factory=list)
    ready_samples: list[str] = field(default_factory=list)

    def to_user_text(self) -> str:
        if self.skipped_reason:
            return self.skipped_reason
        topic_label = " · ".join(self.topic_tokens) or self.topic_raw or "（无）"
        parts = [
            f"话题关键词：{topic_label}",
            "",
            "【说明】门户源拉最新榜/RSS；「主题资讯搜索」= 搜狗资讯+按时间排序，仅保留近45天内。",
            "示例标题≠推送内容。弹窗主推：搜索源→模型一句话总结最新动向；看看别的：四门户随机。",
            "",
            "① 抓取 → ② 去重 → ③ 搜索源模型一句话摘要（弹窗主推）→ 门户入浏览池（看看别的，不要求含话题词）",
            "",
            "来源抓取：",
        ]
        for ln in self.lines:
            if ln.ok:
                samples = "；".join(ln.sample_titles[:3]) if ln.sample_titles else "—"
                parts.append(f"  ✓ {ln.name} ({ln.type})：{ln.count} 条 · 示例 {samples}")
            else:
                parts.append(f"  ✗ {ln.name}：{ln.error or '失败'}")
        parts.extend(
            [
                "",
                f"合计拉取 {self.fetched_total} 条 → 入库候选 {self.new_candidates} 条",
                f"关键词字面命中（标题/摘要含话题词）：{self.keyword_hits} 条",
                f"本次 ready：搜索摘要 {self.search_digest_ready} 条 · 门户浏览 {self.portal_browse_ready} 条",
                f"（rejected {self.ranked_rejected} 条）· 当前 ready 池合计 {self.ready_after} 条",
            ]
        )
        if self.search_digest_ready:
            parts.append("筛选：搜索源已生成一句话摘要（用于自动弹窗）。")
        elif self.topic_tokens:
            parts.append(
                "筛选：搜索源未产出摘要（见上方搜索源错误，或模型超时/未配置 Key）。"
                "自动弹窗只推搜索摘要，与门户热榜是否 ready 无关。"
            )
        if self.portal_browse_ready:
            parts.append(
                f"门户：{self.portal_browse_ready} 条进入浏览池（「看看别的」随机，不按话题词筛）。"
            )
        if self.used_llm:
            parts.append(f"模型调用：{self.llm_batches} 次（主要为搜索摘要）。")
        if self.llm_error:
            parts.append(f"模型异常：{self.llm_error}（可在设置增大 Timeout 后重试）。")
        if self.topic_literal_examples:
            parts.append("")
            parts.append("字面含话题词的抓取示例（仅统计参考）：")
            for line in self.topic_literal_examples[:5]:
                parts.append(f"  · {line}")
        if self.ready_samples:
            parts.append("")
            parts.append("当前 ready 池样本（搜索源为摘要标题 + 一句话正文）：")
            for line in self.ready_samples[:5]:
                parts.append(f"  · {line}")
        if self.llm_payload_preview:
            parts.append("")
            parts.append("传给模型的结构预览（搜索一句话摘要）：")
            parts.append(self.llm_payload_preview)
        if self.push_blocked_by_limit:
            parts.append("")
            parts.append("（今日推送已达上限，本次未弹通知。）")
        return "\n".join(parts)


def _llm_payload_preview(topic: str, batch: list[Candidate], *, mode: str) -> str:
    payload = {
        "mode": mode,
        "topic": topic,
        "candidates": [
            {
                "i": idx,
                "title": c.title[:120],
                "url": c.url,
                "summary": (c.summary or "")[:200],
            }
            for idx, c in enumerate(batch[:3])
        ],
        "note": f"共 {len(batch)} 条，仅展示前 3 条",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def _digest_search_hits(
    client: LLMClient | None,
    topic: str,
    hits: list[Candidate],
    report: ContentCycleReport,
    *,
    use_llm: bool,
) -> SearchTopicDigest | None:
    if not hits:
        return None
    report.llm_payload_preview = _llm_payload_preview(
        topic, hits[:SEARCH_DIGEST_INPUT], mode="search_one_line_summary"
    )
    if use_llm and client:
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                digest = await client.summarize_topic_from_search(
                    topic, hits[:SEARCH_DIGEST_INPUT]
                )
                report.used_llm = True
                report.llm_batches += 1
                report.llm_error = None
                return digest
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if type(exc).__name__ != "ReadTimeout" or attempt == 1:
                    break
        if last_err:
            report.llm_error = type(last_err).__name__
            logger.info("search digest LLM failed: %s", report.llm_error)
            return None
    digest = fallback_search_digest(topic, hits[:SEARCH_DIGEST_INPUT])
    return digest


async def run_content_cycle(
    ctx: "AppContext",
    fetcher: ContentFetcher,
    *,
    only_source_id: int | None = None,
    rank: bool = True,
    respect_daily_limit: bool = True,
    push_if_ready: bool = False,
    on_push: Callable | None = None,
    in_big_fish: bool = False,
) -> ContentCycleReport:
    topic_raw = (ctx.settings.get("today_topic") or "").strip()
    tokens = parse_topic_tokens(topic_raw)
    report = ContentCycleReport(topic_tokens=tokens, topic_raw=topic_raw, lines=[])

    probe_only = only_source_id is not None and not rank
    if not tokens and not probe_only:
        report.skipped_reason = "请先填写「今日话题」（至少一个关键词）。"
        return report

    push_blocked_by_limit = False
    if respect_daily_limit:
        limit = int(ctx.settings.get("content_daily_limit", 6))
        if ctx.content.pushed_today_count() >= limit:
            push_blocked_by_limit = True

    sources = ctx.content.list_sources(enabled_only=True)
    if only_source_id is not None:
        sources = [s for s in sources if s.id == only_source_id]
    if not sources:
        report.skipped_reason = "没有启用的内容来源。可点「恢复默认来源」或自行添加 RSS。"
        return report

    candidates: list[Candidate] = []
    for src in sources:
        line = SourceFetchLine(name=src.name, type=src.type, ok=False)
        if src.fail_count >= 5 and only_source_id is None:
            line.error = "连续失败过多，已暂停（可在来源列表删除后重新添加）"
            report.lines.append(line)
            continue
        try:
            if src.type == "search" and not topic_raw.strip():
                line.error = "需要填写「今日话题」作为检索词"
                report.lines.append(line)
                continue
            items = await fetcher.fetch(src, topic=topic_raw)
            ctx.content.mark_fetch(src.id, True)
            line.ok = True
            line.count = len(items)
            line.sample_titles = [i.title[:60] for i in items[:5]]
            candidates.extend(items)
        except Exception as exc:  # noqa: BLE001
            ctx.content.mark_fetch(src.id, False)
            line.error = str(exc).strip()[:160] or type(exc).__name__
            logger.info("fetch failed %s: %s", src.name, line.error)
        report.lines.append(line)

    report.fetched_total = len(candidates)
    for c in candidates:
        if keyword_score(topic_raw, c.title, c.summary) <= 0:
            continue
        report.topic_literal_examples.append(c.title[:70])
        if len(report.topic_literal_examples) >= 5:
            break
    threshold = float(ctx.settings.get("llm_score_threshold", 0.55))
    client = ctx.build_llm_client()
    use_llm = bool(client and client.api_key and rank and not probe_only)

    search_source_ids = set(ctx.content._search_source_ids())
    search_sources = [s for s in sources if is_search_source(s)]
    search_cfg: dict = {}
    if search_sources:
        try:
            search_cfg = json.loads(search_sources[0].parser_config_json or "{}")
        except json.JSONDecodeError:
            search_cfg = {}
    primary_search_id = search_sources[0].id if search_sources else None

    recent_titles = [
        i.title for i in ctx.content.list_by_status("ready", 100)
    ] + [i.title for i in ctx.content.list_by_status("pushed", 100)]

    search_fresh: list[Candidate] = []
    portal_fresh: list[Candidate] = []
    for c in candidates:
        if not c.url:
            continue
        h = canonical_hash(c.url, c.title)
        if ctx.content.exists_hash(h):
            continue
        if any(title_similar(c.title, t) for t in recent_titles):
            continue
        is_search = c.source_id in search_source_ids if c.source_id is not None else False
        if is_search:
            search_fresh.append(c)
            recent_titles.append(c.title)
            continue
        ctx.content.insert_item(
            h, c.source_id, c.title, c.url, c.published_at, c.summary, status="candidate"
        )
        portal_fresh.append(c)
        recent_titles.append(c.title)

    report.new_candidates = len(portal_fresh) + len(search_fresh)
    report.keyword_hits = count_keyword_hits(topic_raw, candidates, threshold)

    if not rank:
        report.ready_after = len(ctx.content.list_by_status("ready", 500))
        report.push_blocked_by_limit = push_blocked_by_limit
        return report

    if search_fresh and primary_search_id is not None and not probe_only:
        recency_hits = apply_search_recency(
            search_fresh,
            search_cfg,
            max(SEARCH_DIGEST_INPUT * 2, 12),
        )
        digest = await _digest_search_hits(
            client, topic_raw, recency_hits, report, use_llm=use_llm
        )
        if digest and digest.summary.strip() and recency_hits:
            pick = recency_hits[
                min(max(0, digest.pick_i), len(recency_hits) - 1)
            ]
            dhash = search_digest_hash(topic_raw)
            ctx.content.upsert_topic_digest(
                dhash,
                primary_search_id,
                digest.title,
                pick.url,
                pick.published_at,
                pick.summary,
                digest.summary,
                digest.reason or "搜索一句话摘要",
            )
            report.ranked_ready += 1
            report.search_digest_ready += 1

    from fishmate.domain.content import rss_body_excerpt

    for c in portal_fresh:
        h = canonical_hash(c.url, c.title)
        rows = ctx.db.query(
            "SELECT id FROM content_items WHERE canonical_hash=?", (h,)
        )
        if not rows:
            continue
        item_id = rows[0]["id"]
        preview = rss_body_excerpt(c.summary, c.title, max_len=96)
        ctx.content.update_rank(
            item_id,
            0.4,
            "门户浏览池（看看别的）",
            preview,
            "ready",
        )
        report.ranked_ready += 1
        report.portal_browse_ready += 1

    report.ready_after = len(ctx.content.list_by_status("ready", 500))
    for item in ctx.content.list_ready_ordered(5):
        body = (item.short_summary or item.title or "")[:48]
        report.ready_samples.append(f"{item.title[:40]} · {body}")

    if push_if_ready and on_push and not in_big_fish and not push_blocked_by_limit:
        pick = ctx.content.pick_ready_from_search()
        if pick:
            accepted = on_push(pick)
            if accepted:
                ctx.content.set_status(pick.id, "pushed")

    report.push_blocked_by_limit = push_blocked_by_limit
    return report
