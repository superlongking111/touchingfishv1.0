"""Content source adapters: RSS / Web / JSON API / topic search."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup

from fishmate.domain.content import Candidate
from fishmate.domain.search_query import build_search_query, filter_candidates_by_topic
from fishmate.domain.search_recency import apply_search_recency
from fishmate.repositories.content_repo import ContentSource

logger = logging.getLogger("fishmate.content")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 FishMate/1.0"
)
MAX_BODY = 1_500_000
TIMEOUT = 20.0
MAX_REDIRECTS = 3


class ContentFetcher:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=TIMEOUT,
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                headers={"User-Agent": USER_AGENT},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch(self, source: ContentSource, *, topic: str = "") -> list[Candidate]:
        if source.type == "search":
            return await self._fetch_search(source, topic)
        url = source.url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("only http/https allowed")
        if source.type == "rss":
            return await self._fetch_rss(source)
        if source.type == "json":
            return await self._fetch_json(source)
        if source.type == "web":
            return await self._fetch_web(source)
        raise ValueError(f"unknown source type: {source.type}")

    async def _read(self, url: str) -> str:
        client = await self._get_client()
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > MAX_BODY:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")

    async def _fetch_rss(self, source: ContentSource) -> list[Candidate]:
        text = await self._read(source.url)
        parsed = feedparser.parse(text)
        items: list[Candidate] = []
        for entry in parsed.entries[:40]:
            title = getattr(entry, "title", "") or ""
            link = getattr(entry, "link", "") or ""
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            published = None
            if getattr(entry, "published", None):
                published = entry.published
            items.append(
                Candidate(
                    title=BeautifulSoup(title, "html.parser").get_text(" ", strip=True),
                    url=link,
                    summary=BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)[:800],
                    published_at=published,
                    source_id=source.id,
                )
            )
        return items

    def _parser_config(self, source: ContentSource) -> dict[str, Any]:
        if not source.parser_config_json:
            return {}
        try:
            return json.loads(source.parser_config_json)
        except json.JSONDecodeError:
            return {}

    async def _fetch_web(self, source: ContentSource) -> list[Candidate]:
        cfg = self._parser_config(source)
        item_sel = cfg.get("item_selector", "article a, .post a, h2 a, h3 a")
        text = await self._read(source.url)
        soup = BeautifulSoup(text, "html.parser")
        seen: set[str] = set()
        items: list[Candidate] = []
        for a in soup.select(item_sel)[:40]:
            href = a.get("href")
            title = a.get_text(" ", strip=True)
            if not href or not title or len(title) < 4:
                continue
            full = urljoin(source.url, href)
            if full in seen:
                continue
            seen.add(full)
            items.append(
                Candidate(
                    title=title[:200],
                    url=full,
                    summary=title[:400],
                    source_id=source.id,
                )
            )
        return items

    async def _fetch_search(self, source: ContentSource, topic: str) -> list[Candidate]:
        query = topic.strip()
        if not query:
            raise ValueError("search 需要今日话题作为检索词")
        cfg = self._parser_config(source)
        topic_raw = query
        query = build_search_query(topic_raw, cfg)
        provider = (source.url.strip() or cfg.get("provider") or "sogou").lower()
        max_results = int(cfg.get("max_results", 10))
        max_results = max(3, min(max_results, 15))
        fetch_limit = min(max_results * 4, 40)
        if provider == "bing_cn":
            items = await self._search_bing_cn(query, source.id, fetch_limit, cfg)
        elif provider == "sogou":
            items = await self._search_sogou(query, source.id, fetch_limit, cfg)
        elif provider == "duckduckgo":
            items = await self._search_duckduckgo(query, source.id, fetch_limit, cfg)
        else:
            raise ValueError(f"unsupported search provider: {provider}")
        before_topic = items
        items = filter_candidates_by_topic(items, topic_raw)
        if not items and before_topic:
            # 已按检索词搜过；标题/摘要未字面含词时仍交给摘要模型
            items = before_topic[:fetch_limit]
        items = apply_search_recency(items, cfg, max_results)
        if not items:
            raise ValueError(
                "search: 无近期资讯（已按时间过滤，可放宽 max_recency_days 或换话题）"
            )
        return items

    @staticmethod
    def _search_should_skip(href: str, title: str, cfg: dict) -> bool:
        low_url = href.lower()
        for dom in cfg.get("block_domains") or []:
            if dom.lower() in low_url:
                return True
        for kw in cfg.get("block_title_keywords") or []:
            if kw in title:
                return True
        return False

    async def _search_duckduckgo(
        self,
        query: str,
        source_id: int | None,
        limit: int,
        cfg: dict,
    ) -> list[Candidate]:
        client = await self._get_client()
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "cn-zh"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        items: list[Candidate] = []
        for block in soup.select(".result"):
            if len(items) >= limit:
                break
            a = block.select_one("a.result__a")
            snippet = block.select_one(".result__snippet")
            if not a:
                continue
            href = (a.get("href") or "").strip()
            title = a.get_text(" ", strip=True)
            if not href or not title:
                continue
            if href.startswith("//"):
                href = "https:" + href
            if href in seen:
                continue
            if self._search_should_skip(href, title, cfg):
                continue
            seen.add(href)
            summary = snippet.get_text(" ", strip=True) if snippet else title
            items.append(
                Candidate(
                    title=title[:200],
                    url=href,
                    summary=summary[:800],
                    source_id=source_id,
                )
            )
        if not items:
            raise ValueError("search returned no results")
        return items

    async def _search_bing_cn(
        self,
        query: str,
        source_id: int | None,
        limit: int,
        cfg: dict,
    ) -> list[Candidate]:
        client = await self._get_client()
        resp = await client.get(
            "https://cn.bing.com/news/search",
            params={
                "q": query,
                "qft": "interval%3d%227%22",
                "form": "PTFTNR",
            },
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        items: list[Candidate] = []
        for block in soup.select(".news-card, li.b_algo"):
            if len(items) >= limit:
                break
            a = block.select_one("a.title") or block.select_one("h2 a")
            caption = block.select_one(".snippet") or block.select_one(".b_caption p")
            if not a:
                continue
            href = (a.get("href") or "").strip()
            title = a.get_text(" ", strip=True)
            if not href.startswith("http") or not title:
                continue
            if href in seen or self._search_should_skip(href, title, cfg):
                continue
            seen.add(href)
            summary = caption.get_text(" ", strip=True) if caption else title
            items.append(
                Candidate(
                    title=title[:200],
                    url=href,
                    summary=summary[:800],
                    source_id=source_id,
                )
            )
        if not items:
            raise ValueError("search returned no results")
        return items

    async def _search_sogou(
        self,
        query: str,
        source_id: int | None,
        limit: int,
        cfg: dict,
    ) -> list[Candidate]:
        client = await self._get_client()
        resp = await client.get(
            "https://www.sogou.com/web",
            params={
                "query": query,
                "mode": "3",
                "sort": "1",
            },
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        items: list[Candidate] = []
        selectors = ".vrwrap, .rb, .result, .news-list li, .news-box"
        for block in soup.select(selectors):
            if len(items) >= limit:
                break
            a = block.select_one("h3 a") or block.select_one("a")
            snippet = (
                block.select_one(".str-info")
                or block.select_one(".str_text")
                or block.select_one(".news-text")
            )
            if not a:
                continue
            href = (a.get("href") or "").strip()
            if href.startswith("/"):
                href = urljoin("https://www.sogou.com", href)
            title = a.get_text(" ", strip=True)
            if not title or not href.startswith("http"):
                continue
            if href in seen or self._search_should_skip(href, title, cfg):
                continue
            seen.add(href)
            summary = snippet.get_text(" ", strip=True) if snippet else title
            items.append(
                Candidate(
                    title=title[:200],
                    url=href,
                    summary=summary[:800],
                    source_id=source_id,
                )
            )
        if not items:
            news_resp = await client.get(
                "https://news.sogou.com/news",
                params={"query": query, "sort": "1"},
            )
            news_resp.raise_for_status()
            news_soup = BeautifulSoup(news_resp.text, "html.parser")
            for block in news_soup.select(".news-list li, .result, .vrwrap"):
                if len(items) >= limit:
                    break
                a = block.select_one("a")
                if not a:
                    continue
                href = (a.get("href") or "").strip()
                title = a.get_text(" ", strip=True)
                if not href.startswith("http") or not title:
                    continue
                if href in seen or self._search_should_skip(href, title, cfg):
                    continue
                seen.add(href)
                items.append(
                    Candidate(
                        title=title[:200],
                        url=href,
                        summary=title[:800],
                        source_id=source_id,
                    )
                )
        if not items:
            raise ValueError("search: 搜狗未解析到结果（可能页面结构变化或网络拦截）")
        return items

    async def _fetch_json(self, source: ContentSource) -> list[Candidate]:
        cfg = self._parser_config(source)
        text = await self._read(source.url)
        data = json.loads(text)
        code_path = cfg.get("success_code_path")
        if code_path:
            node = data
            for part in code_path.split("."):
                if part:
                    node = node[part]
            expected = cfg.get("success_code_value", 0)
            if node != expected:
                raise ValueError(f"api code {node!r} != {expected!r}")
        list_path = cfg.get("list_path", "")
        title_key = cfg.get("title_key", "title")
        url_key = cfg.get("url_key", "url")
        summary_key = cfg.get("summary_key", "summary")
        url_prefix = cfg.get("url_prefix", "")
        url_suffix = cfg.get("url_suffix", "")
        nodes = data
        if list_path:
            for part in list_path.split("."):
                if part:
                    nodes = nodes[part]
        if not isinstance(nodes, list):
            raise ValueError("json list_path did not resolve to list")
        items: list[Candidate] = []
        for node in nodes[:40]:
            if not isinstance(node, dict):
                continue
            title = str(node.get(title_key, "")).strip()
            link = str(node.get(url_key, "")).strip()
            summary = str(node.get(summary_key, title)).strip()
            if not title or not link:
                continue
            if not link.startswith("http://") and not link.startswith("https://"):
                link = f"{url_prefix}{link}{url_suffix}"
            items.append(
                Candidate(
                    title=title[:200],
                    url=link,
                    summary=summary[:800],
                    source_id=source.id,
                )
            )
        return items
