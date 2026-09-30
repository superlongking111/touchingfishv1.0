import asyncio

from fishmate.repositories.content_repo import ContentSource
from fishmate.services.content_fetcher import ContentFetcher

BING_SAMPLE = """
<ul><li class="b_algo">
<h2><a href="https://www.sohu.com/a/123">猫娘相关新闻标题</a></h2>
<div class="b_caption"><p>2026-09-20 摘要内容在这里</p></div>
</li></ul>
"""


def test_bing_cn_parse(monkeypatch):
    fetcher = ContentFetcher()
    source = ContentSource(
        1,
        "s",
        "search",
        "bing_cn",
        True,
        '{"max_recency_days": 45}',
        None,
        0,
    )

    async def fake_get(url, params=None):
        class R:
            text = BING_SAMPLE

            def raise_for_status(self):
                pass

        return R()

    async def run():
        client = await fetcher._get_client()
        monkeypatch.setattr(client, "get", fake_get)
        return await fetcher.fetch(source, topic="猫娘")

    items = asyncio.run(run())
    assert len(items) == 1
    assert "sohu.com" in items[0].url
    assert "摘要" in items[0].summary
