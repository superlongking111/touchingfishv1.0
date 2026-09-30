"""OpenAI-compatible LLM client."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from fishmate.domain.content import (
    LLM_SUMMARY_TARGET,
    Candidate,
    RankedItem,
    SearchTopicDigest,
)

logger = logging.getLogger("fishmate.llm")


@dataclass
class TestResult:
    ok: bool
    message: str
    latency_ms: int = 0


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: float = 30.0,
        temperature: float = 0.3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def test_connection(self) -> TestResult:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.base_url}/chat/completions"
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                    "temperature": 0,
                }
                resp = await client.post(url, headers=self._headers(), json=payload)
                latency = int((time.perf_counter() - started) * 1000)
                if resp.status_code >= 400:
                    # Never log body which may echo keys
                    return TestResult(False, f"HTTP {resp.status_code}", latency)
                return TestResult(True, "连接成功", latency)
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - started) * 1000)
            return TestResult(False, f"{type(exc).__name__}", latency)

    async def _chat(self, system: str, user: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self.temperature,
            }
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    @staticmethod
    def _extract_json(text: str) -> Any:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if m:
            return json.loads(m.group(0))
        raise ValueError("invalid json from model")

    async def rank_content(self, topic: str, items: list[Candidate]) -> list[RankedItem]:
        if not items:
            return []
        if not self.api_key:
            raise RuntimeError("no api key")
        payload = [
            {
                "i": idx,
                "title": c.title,
                "url": c.url,
                "summary": (c.summary or "")[:500],
            }
            for idx, c in enumerate(items)
        ]
        system = (
            "你是内容筛选助手。用户有一个「今日话题」，从 candidates 里找出"
            "与话题相关、偏时效的资讯/报道/动态（优先新闻口吻，降低百科、教程、壁纸类）。"
            "含同义与亚文化关联（如猫娘↔nekomimi），不要硬蹭无关热点。"
            "只返回 JSON 数组；每条必须包含字段："
            "i（整数，等于 candidates 里该条目的 i，从 0 起，禁止编造序号）、"
            "relevance、interest（0-1）、reason、short_summary。"
            f"short_summary 是给桌面弹窗用的{LLM_SUMMARY_TARGET}中文摘要，"
            "不要重复标题、不要 markdown、不要 URL。"
            "relevance/interest 为 0-1。不要编造 URL。不相关的条目不要返回。"
        )
        user = json.dumps({"topic": topic, "candidates": payload}, ensure_ascii=False)
        raw = await self._chat(system, user)
        arr = self._extract_json(raw)
        if not isinstance(arr, list):
            raise ValueError("rank result not list")
        ranked: list[RankedItem] = []
        for row in arr:
            try:
                idx = int(row["i"])
                if idx < 0 or idx >= len(items):
                    continue
                c = items[idx]
                ranked.append(
                    RankedItem(
                        candidate=c,
                        relevance=float(row.get("relevance", 0)),
                        interest=float(row.get("interest", 0)),
                        reason=str(row.get("reason", ""))[:300],
                        short_summary=str(row.get("short_summary", c.title))[:120],
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return ranked

    async def summarize_topic_from_search(
        self, topic: str, items: list[Candidate]
    ) -> SearchTopicDigest:
        """One-shot semantic summary for toast; search results are already topic-filtered."""
        if not items:
            raise ValueError("no search hits")
        if not self.api_key:
            raise RuntimeError("no api key")
        payload = [
            {
                "i": idx,
                "title": c.title,
                "url": c.url,
                "summary": (c.summary or "")[:400],
                "published_at": c.published_at,
            }
            for idx, c in enumerate(items)
        ]
        system = (
            "你是桌面资讯助手。用户已用「今日话题」在搜狗资讯搜到一批最新结果，"
            "条目本身已按主题检索，无需再对每条做相关性打分或排序。"
            "请通读标题与摘要，用模型擅长的方式概括：最近关于该话题有什么新动向。"
            "只返回一个 JSON 对象（不是数组），字段："
            f"title（弹窗标题，10-18 字，可含话题词，勿照搬某条新闻标题）、"
            f"summary（弹窗正文，{LLM_SUMMARY_TARGET}，一句话，中文，"
            "不要 markdown、不要 URL、不要列表、不要「据悉」开头）、"
            "i（整数，最适合作为阅读原文链接的 candidates 序号，从 0 起）、"
            "reason（20 字内备注，可选）。"
        )
        user = json.dumps({"topic": topic, "candidates": payload}, ensure_ascii=False)
        raw = await self._chat(system, user)
        obj = self._extract_json(raw)
        if not isinstance(obj, dict):
            raise ValueError("digest result not object")
        idx = int(obj.get("i", 0))
        idx = max(0, min(idx, len(items) - 1))
        title = str(obj.get("title", topic))[:40]
        summary = str(obj.get("summary", ""))[:120].strip()
        if not summary:
            raise ValueError("empty summary from model")
        reason = str(obj.get("reason", ""))[:80]
        return SearchTopicDigest(title=title, summary=summary, pick_i=idx, reason=reason)

    async def draft_daily_report(self, events_payload: dict, notes: str = "") -> str:
        if not self.api_key:
            raise RuntimeError("no api key")
        system = (
            "你是工作日报草稿助手。规则：\n"
            "1. 不虚构完成事项；\n"
            "2. 将同一文件的重复事件聚合；\n"
            "3. 输出「完成 / 进行中 / 待处理」三段；\n"
            "4. 无证据的信息不要写；\n"
            "5. 开头注明【草稿】；\n"
            "6. 只基于事件元数据和用户备注，不假设文件内容。"
        )
        user = json.dumps(events_payload, ensure_ascii=False)
        return await self._chat(system, user)
