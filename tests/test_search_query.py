from fishmate.domain.content import Candidate
from fishmate.domain.search_query import (
    build_search_query,
    filter_candidates_by_topic,
    search_result_matches_topic,
)


def test_build_search_query():
    q = build_search_query(
        "伪娘", {"query_suffix": " 新闻", "append_current_year": False}
    )
    assert q == "伪娘 新闻"
    q2 = build_search_query("伪娘", {"query_suffix": " 新闻"})
    assert "最新" in q2 and "新闻" in q2


def test_filter_drops_single_char_dict():
    items = [
        Candidate("伪 的意思, 伪 的拼音", "https://z.com/1", "释义"),
        Candidate("伪娘助阵游戏展-中新网", "https://news.com/2", "报道"),
    ]
    kept = filter_candidates_by_topic(items, "伪娘")
    assert len(kept) == 1
    assert "中新网" in kept[0].title


def test_match_requires_full_token():
    assert not search_result_matches_topic("伪的拼音", "wěi", "伪娘")
    assert search_result_matches_topic("关于伪娘的报道", "", "伪娘")
