from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fishmate.domain.sources import is_portal_source, is_search_source

from .db import Database


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


_BILI_PARSER = json.dumps(
    {
        "list_path": "data.list",
        "title_key": "title",
        "url_key": "bvid",
        "summary_key": "desc",
        "url_prefix": "https://www.bilibili.com/video/",
        "success_code_path": "code",
        "success_code_value": 0,
    },
    ensure_ascii=False,
)

_SEARCH_PARSER = json.dumps(
    {
        "provider": "sogou",
        "max_results": 10,
        "query_suffix": " 新闻",
        "max_recency_days": 45,
        "append_current_year": True,
        "block_domains": [
            "baike.baidu.com",
            "m.baike.com",
            "hanyuguoxue.com",
            "chagushici.com",
            "hgcha.com",
            "zidian.",
            "cidian.",
            "zhihu.com",
            "zhuanlan.zhihu.com",
            "moegirl.org.cn",
            "wikipedia.org",
            "haowallpaper.com",
            "pixabay.com",
            "duckduckgo.com",
        ],
        "block_title_keywords": [
            "百科",
            "萌娘百科",
            "壁纸",
            "知乎专栏",
            "免费图片",
            "拼音",
            "部首",
            "笔顺",
            "汉语字典",
            "新华字典",
            "的意思,",
            "字的意思",
        ],
    },
    ensure_ascii=False,
)

_TOUTIAO_PARSER = json.dumps(
    {
        "list_path": "data",
        "title_key": "Title",
        "url_key": "Url",
        "summary_key": "Title",
    },
    ensure_ascii=False,
)

# 预设：主题资讯搜索（入口）+ 四门户（看看别的）
DEFAULT_CONTENT_SOURCES: list[tuple[str, str, str, str | None]] = [
    (
        "主题资讯搜索 · 入口",
        "search",
        "sogou",
        _SEARCH_PARSER,
    ),
    ("ACG17 · 二次元", "rss", "https://www.acg17.com/feed", None),
    ("新浪 · 要闻", "rss", "http://rss.sina.com.cn/news/china/focus15.xml", None),
    (
        "Bilibili · 综合排行榜",
        "json",
        "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
        _BILI_PARSER,
    ),
    (
        "今日头条 · 热榜",
        "json",
        "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        _TOUTIAO_PARSER,
    ),
]

DEFAULT_SOURCE_KEYS: frozenset[tuple[str, str]] = frozenset(
    (type_, url.rstrip("/")) for _, type_, url, _ in DEFAULT_CONTENT_SOURCES
)

@dataclass
class ContentSource:
    id: int
    name: str
    type: str
    url: str
    enabled: bool
    parser_config_json: str | None
    last_fetch_at: str | None
    fail_count: int


@dataclass
class ContentItem:
    id: int
    canonical_hash: str
    source_id: int | None
    title: str
    url: str
    published_at: str | None
    summary: str | None
    llm_score: float | None
    llm_reason: str | None
    short_summary: str | None
    status: str
    created_at: str


class ContentRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def seed_defaults(self) -> None:
        count = self.db.query_one("SELECT COUNT(*) AS c FROM content_sources")
        if count and count["c"] > 0:
            return
        for name, type_, url, cfg in DEFAULT_CONTENT_SOURCES:
            self.add_source(name, type_, url, cfg, enabled=True)

    def ensure_default_sources(self) -> int:
        """Add preset sources whose URL is not yet in the list."""
        existing = {s.url.rstrip("/") for s in self.list_sources()}
        added = 0
        for name, type_, url, cfg in DEFAULT_CONTENT_SOURCES:
            key = url.rstrip("/")
            if key in existing:
                continue
            self.add_source(name, type_, url, cfg, enabled=True)
            existing.add(key)
            added += 1
        return added

    def remove_non_default_presets(self) -> int:
        removed = 0
        for s in self.list_sources():
            key = (s.type, s.url.rstrip("/"))
            if key in DEFAULT_SOURCE_KEYS:
                continue
            self.delete_source(s.id)
            removed += 1
        return removed

    def refresh_preset_sources(self) -> tuple[int, int]:
        """Drop sources not in current defaults, add missing defaults."""
        removed = self.remove_non_default_presets()
        added = self.ensure_default_sources()
        return removed, added

    def list_sources(self, enabled_only: bool = False) -> list[ContentSource]:
        sql = "SELECT * FROM content_sources"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY id"
        rows = self.db.query(sql)
        return [
            ContentSource(
                id=r["id"],
                name=r["name"],
                type=r["type"],
                url=r["url"],
                enabled=bool(r["enabled"]),
                parser_config_json=r["parser_config_json"],
                last_fetch_at=r["last_fetch_at"],
                fail_count=r["fail_count"] or 0,
            )
            for r in rows
        ]

    def add_source(
        self,
        name: str,
        type_: str,
        url: str,
        parser_config_json: str | None = None,
        enabled: bool = True,
    ) -> int:
        cur = self.db.execute(
            """
            INSERT INTO content_sources(name,type,url,enabled,parser_config_json,fail_count)
            VALUES(?,?,?,?,?,0)
            """,
            (name, type_, url, 1 if enabled else 0, parser_config_json),
        )
        return int(cur.lastrowid)

    def update_source(self, source: ContentSource) -> None:
        self.db.execute(
            """
            UPDATE content_sources SET
              name=?, type=?, url=?, enabled=?, parser_config_json=?,
              last_fetch_at=?, fail_count=?
            WHERE id=?
            """,
            (
                source.name,
                source.type,
                source.url,
                1 if source.enabled else 0,
                source.parser_config_json,
                source.last_fetch_at,
                source.fail_count,
                source.id,
            ),
        )

    def delete_source(self, source_id: int) -> None:
        self.db.execute("DELETE FROM content_items WHERE source_id=?", (source_id,))
        self.db.execute("DELETE FROM content_sources WHERE id=?", (source_id,))

    def mark_fetch(self, source_id: int, ok: bool) -> None:
        if ok:
            self.db.execute(
                "UPDATE content_sources SET last_fetch_at=?, fail_count=0 WHERE id=?",
                (_now(), source_id),
            )
        else:
            self.db.execute(
                "UPDATE content_sources SET fail_count=fail_count+1, last_fetch_at=? WHERE id=?",
                (_now(), source_id),
            )

    def exists_hash(self, canonical_hash: str) -> bool:
        row = self.db.query_one(
            "SELECT 1 FROM content_items WHERE canonical_hash=?",
            (canonical_hash,),
        )
        return row is not None

    def insert_item(
        self,
        canonical_hash: str,
        source_id: int | None,
        title: str,
        url: str,
        published_at: str | None,
        summary: str | None,
        status: str = "candidate",
        llm_score: float | None = None,
        llm_reason: str | None = None,
        short_summary: str | None = None,
    ) -> int | None:
        if self.exists_hash(canonical_hash):
            return None
        try:
            cur = self.db.execute(
                """
                INSERT INTO content_items(
                  canonical_hash,source_id,title,url,published_at,summary,
                  llm_score,llm_reason,short_summary,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    canonical_hash,
                    source_id,
                    title,
                    url,
                    published_at,
                    summary,
                    llm_score,
                    llm_reason,
                    short_summary,
                    status,
                    _now(),
                ),
            )
            return int(cur.lastrowid)
        except Exception:
            return None

    def upsert_topic_digest(
        self,
        digest_hash: str,
        source_id: int,
        title: str,
        url: str,
        published_at: str | None,
        summary: str | None,
        short_summary: str,
        reason: str,
        score: float = 1.0,
    ) -> int:
        """One ready row per topic per day — LLM one-liner for search auto-push."""
        row = self.db.query_one(
            "SELECT id FROM content_items WHERE canonical_hash=?",
            (digest_hash,),
        )
        if row:
            item_id = int(row["id"])
            self.db.execute(
                """
                UPDATE content_items SET
                  title=?, url=?, published_at=?, summary=?,
                  llm_score=?, llm_reason=?, short_summary=?, status='ready', created_at=?
                WHERE id=?
                """,
                (
                    title,
                    url,
                    published_at,
                    summary,
                    score,
                    reason,
                    short_summary,
                    _now(),
                    item_id,
                ),
            )
            return item_id
        cur = self.db.execute(
            """
            INSERT INTO content_items(
              canonical_hash,source_id,title,url,published_at,summary,
              llm_score,llm_reason,short_summary,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                digest_hash,
                source_id,
                title,
                url,
                published_at,
                summary,
                score,
                reason,
                short_summary,
                "ready",
                _now(),
            ),
        )
        return int(cur.lastrowid)

    def update_rank(
        self,
        item_id: int,
        score: float,
        reason: str,
        short_summary: str,
        status: str,
    ) -> None:
        self.db.execute(
            """
            UPDATE content_items SET
              llm_score=?, llm_reason=?, short_summary=?, status=?
            WHERE id=?
            """,
            (score, reason, short_summary, status, item_id),
        )

    def list_by_status(self, status: str, limit: int = 50) -> list[ContentItem]:
        rows = self.db.query(
            """
            SELECT * FROM content_items WHERE status=?
            ORDER BY created_at DESC LIMIT ?
            """,
            (status, limit),
        )
        return [self._item(r) for r in rows]

    def get_item(self, item_id: int) -> ContentItem | None:
        row = self.db.query_one("SELECT * FROM content_items WHERE id=?", (item_id,))
        return self._item(row) if row else None

    def set_status(self, item_id: int, status: str) -> None:
        self.db.execute(
            "UPDATE content_items SET status=? WHERE id=?",
            (status, item_id),
        )

    def list_ready_ordered(self, limit: int = 50) -> list[ContentItem]:
        rows = self.db.query(
            """
            SELECT * FROM content_items
            WHERE status='ready'
            ORDER BY COALESCE(llm_score,0) DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._item(r) for r in rows]

    def pick_ready(self) -> ContentItem | None:
        items = self.list_ready_ordered(1)
        return items[0] if items else None

    def pick_random_ready(self, pool_limit: int = 80) -> ContentItem | None:
        items = self.list_ready_ordered(pool_limit)
        if not items:
            return None
        return random.choice(items)

    def list_browse_pool(self, limit: int = 60) -> list[ContentItem]:
        seen: set[int] = set()
        out: list[ContentItem] = []
        for status in ("ready", "pushed", "candidate"):
            for item in self.list_by_status(status, limit):
                if item.id in seen:
                    continue
                seen.add(item.id)
                out.append(item)
                if len(out) >= limit:
                    return out
        return out

    def _search_source_ids(self) -> list[int]:
        return [
            s.id
            for s in self.list_sources(enabled_only=True)
            if is_search_source(s)
        ]

    def pick_ready_from_search(self) -> ContentItem | None:
        """Auto-push: 主题搜索的一句话摘要（非逐条排序取第一）."""
        ids = self._search_source_ids()
        if not ids:
            return None
        placeholders = ",".join("?" * len(ids))
        row = self.db.query_one(
            f"""
            SELECT * FROM content_items
            WHERE status='ready' AND source_id IN ({placeholders})
            ORDER BY created_at DESC, COALESCE(llm_score,0) DESC
            LIMIT 1
            """,
            tuple(ids),
        )
        return self._item(row) if row else None

    def pick_random_portal_ready(
        self, exclude_ids: set[int] | None = None
    ) -> ContentItem | None:
        """「看看别的」：在四门户中随机选一个源，再随机一条 ready。"""
        skip = exclude_ids or set()
        portal_ids = [
            s.id
            for s in self.list_sources(enabled_only=True)
            if is_portal_source(s)
        ]
        if not portal_ids:
            return None
        by_source: dict[int, list[Any]] = {}
        for sid in portal_ids:
            rows = self.db.query(
                """
                SELECT * FROM content_items
                WHERE status='ready' AND source_id=?
                """,
                (sid,),
            )
            filtered = [r for r in rows if r["id"] not in skip]
            if filtered:
                by_source[sid] = filtered
        if not by_source:
            return None
        sid = random.choice(list(by_source.keys()))
        row = random.choice(by_source[sid])
        return self._item(row)

    def pushed_today_count(self) -> int:
        """仅统计系统自动弹窗推送（status=pushed），不含「看看别的」浏览。"""
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.db.query_one(
            """
            SELECT COUNT(*) AS c FROM content_items
            WHERE status='pushed' AND date(created_at)=?
            """,
            (today,),
        )
        return int(row["c"]) if row else 0

    def purge_older_than(self, days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        cur = self.db.execute(
            "DELETE FROM content_items WHERE created_at < ?",
            (cutoff,),
        )
        return cur.rowcount

    def clear_all(self) -> None:
        self.db.execute("DELETE FROM content_items")

    @staticmethod
    def _item(r: Any) -> ContentItem:
        return ContentItem(
            id=r["id"],
            canonical_hash=r["canonical_hash"],
            source_id=r["source_id"],
            title=r["title"],
            url=r["url"],
            published_at=r["published_at"],
            summary=r["summary"],
            llm_score=r["llm_score"],
            llm_reason=r["llm_reason"],
            short_summary=r["short_summary"] if "short_summary" in r.keys() else None,
            status=r["status"],
            created_at=r["created_at"],
        )
