import asyncio
import json
from pathlib import Path

from fishmate.domain.content import (
    Candidate,
    fallback_search_digest,
    search_digest_hash,
)
from fishmate.repositories.content_repo import ContentRepo
from fishmate.repositories.db import Database
from fishmate.services.llm_client import LLMClient


def test_search_digest_hash_stable_per_day():
    h1 = search_digest_hash("猫娘", "2026-03-29")
    h2 = search_digest_hash("猫娘", "2026-03-29")
    h3 = search_digest_hash("猫娘", "2026-03-30")
    assert h1 == h2
    assert h1 != h3


def test_fallback_search_digest():
    hits = [
        Candidate(title="A", url="https://a", summary="摘要A"),
        Candidate(title="B", url="https://b", summary="摘要B"),
    ]
    d = fallback_search_digest("伪娘", hits)
    assert "伪娘" in d.title
    assert d.summary == "摘要A"
    assert d.pick_i == 0


def test_upsert_topic_digest_one_per_day(tmp_path: Path):
    db = Database(tmp_path / "d.db")
    db.migrate()
    repo = ContentRepo(db)
    repo.seed_defaults()
    sid = repo._search_source_ids()[0]
    h = search_digest_hash("测试话题")
    id1 = repo.upsert_topic_digest(
        h,
        sid,
        "标题一",
        "https://example.com/1",
        None,
        "raw",
        "一句话摘要",
        "reason",
    )
    id2 = repo.upsert_topic_digest(
        h,
        sid,
        "标题二",
        "https://example.com/2",
        None,
        "raw2",
        "更新摘要",
        "reason2",
    )
    assert id1 == id2
    item = repo.get_item(id1)
    assert item is not None
    assert item.title == "标题二"
    assert item.short_summary == "更新摘要"
    assert item.status == "ready"
    db.close()


def test_summarize_topic_from_search_parses_object():
    client = LLMClient("https://api.example.com/v1", "sk-test", "m")
    payload = {
        "title": "猫娘圈近况",
        "summary": "近期多款手游与联动活动围绕猫娘题材展开，社区讨论集中在立绘与配音方向。",
        "i": 1,
        "reason": "ok",
    }

    async def fake_chat(_s: str, _u: str) -> str:
        return json.dumps(payload, ensure_ascii=False)

    client._chat = fake_chat  # type: ignore[method-assign]
    hits = [
        Candidate(title="t0", url="https://0", summary="s0"),
        Candidate(title="t1", url="https://1", summary="s1"),
    ]

    digest = asyncio.run(client.summarize_topic_from_search("猫娘", hits))
    assert digest.title == payload["title"]
    assert digest.summary == payload["summary"]
    assert digest.pick_i == 1
