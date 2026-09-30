from pathlib import Path

from fishmate.repositories.content_repo import ContentRepo, DEFAULT_CONTENT_SOURCES
from fishmate.repositories.db import Database
from fishmate.domain.content import canonical_hash


def test_pick_search_vs_portal(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    repo = ContentRepo(db)
    repo.seed_defaults()
    sources = {s.name: s for s in repo.list_sources()}
    search_id = sources["主题资讯搜索 · 入口"].id
    bili_id = sources["Bilibili · 综合排行榜"].id
    h1 = canonical_hash("https://news.example/1", "Search hit")
    h2 = canonical_hash("https://bilibili.com/1", "Bili")
    id1 = repo.insert_item(
        h1, search_id, "Search hit", "https://news.example/1", None, "s", status="ready"
    )
    id2 = repo.insert_item(
        h2, bili_id, "Bili", "https://bilibili.com/1", None, "s", status="ready"
    )
    assert id1 and id2
    repo.update_rank(id1, 0.9, "r", "摘要一", "ready")
    repo.update_rank(id2, 0.95, "r", "摘要二", "ready")
    top = repo.pick_ready_from_search()
    assert top is not None
    assert top.source_id == search_id
    portal = repo.pick_random_portal_ready(set())
    assert portal is not None
    assert portal.source_id != search_id
    db.close()
