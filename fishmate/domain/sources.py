"""Preset portal vs search source classification."""

from __future__ import annotations

from typing import Protocol


class _SourceLike(Protocol):
    name: str
    type: str
    url: str


def is_search_source(source: _SourceLike) -> bool:
    return source.type == "search"


def is_portal_source(source: _SourceLike) -> bool:
    """Bilibili / 新浪 / 今日头条 / ACG17 — used for「看看别的」随机展示。"""
    if source.type == "search":
        return False
    name = source.name.lower()
    url = source.url.lower()
    if "bilibili" in name or "bilibili.com" in url:
        return True
    if "新浪" in source.name:
        return True
    if "头条" in source.name or "toutiao.com" in url:
        return True
    if "acg17" in name or "acg17.com" in url:
        return True
    return False
