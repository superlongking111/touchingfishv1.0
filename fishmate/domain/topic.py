"""Today topic parsing for keyword match / LLM input."""

from __future__ import annotations

import re

# 多个关键词之间用分隔符；词组内可含空格（如 AI Agent 视为一个关键词）
TOPIC_SPLIT_RE = re.compile(r"[,，、/|;；\n\r\t]+")

TOPIC_SEPARATOR_HINT = (
    "多个词用逗号、顿号、/ 或 | 分隔；例：猫娘, 新番。"
    "「主题资讯搜索」默认搜狗新闻向检索，须配模型做语义筛选。"
)


def parse_topic_tokens(topic: str) -> list[str]:
    """Split topic into non-empty tokens for matching."""
    if not topic or not topic.strip():
        return []
    parts = TOPIC_SPLIT_RE.split(topic.strip())
    seen: set[str] = set()
    tokens: list[str] = []
    for p in parts:
        t = p.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(t)
    return tokens


def topic_display_summary(topic: str) -> str:
    tokens = parse_topic_tokens(topic)
    if not tokens:
        return "（未设置话题）"
    return " · ".join(tokens)
