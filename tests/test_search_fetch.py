import asyncio

from bs4 import BeautifulSoup

from fishmate.repositories.content_repo import ContentSource
from fishmate.services.content_fetcher import ContentFetcher


SAMPLE_HTML = """
<div class="result">
  <a class="result__a" href="https://example.com/a">猫娘百科</a>
  <div class="result__snippet">二次元猫耳少女</div>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/b">Another</a>
</div>
"""


def test_parse_duckduckgo_html():
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    titles = [a.get_text(strip=True) for a in soup.select("a.result__a")]
    assert titles == ["猫娘百科", "Another"]


def test_search_fetch_from_html(monkeypatch):
    fetcher = ContentFetcher()
    source = ContentSource(
        1,
        "test",
        "search",
        "bing_cn",
        True,
        '{"max_results": 5, "max_recency_days": 45}',
        None,
        0,
    )

    bing_html = """
    <li class="b_algo"><h2><a href="https://example.com/a">猫娘百科</a></h2>
        <div class="b_caption"><p>2026-09-28 二次元猫耳少女</p></div></li>
    <li class="b_algo"><h2><a href="https://example.com/b">Another</a></h2></li>
    """

    async def fake_get(url, params=None):
        class R:
            text = bing_html

            def raise_for_status(self):
                pass

        return R()

    async def run():
        client = await fetcher._get_client()
        monkeypatch.setattr(client, "get", fake_get)
        return await fetcher.fetch(source, topic="猫娘")

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0].title == "猫娘百科"
    assert "example.com" in items[0].url
