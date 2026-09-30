from fishmate.domain.topic import parse_topic_tokens, topic_display_summary


def test_parse_topic_separators():
    t = "AI Agent, 大模型 / 自动化|测试；foo、bar"
    tokens = parse_topic_tokens(t)
    assert tokens == ["AI Agent", "大模型", "自动化", "测试", "foo", "bar"]


def test_parse_dedupe():
    assert parse_topic_tokens("ai, AI ,ai") == ["ai"]


def test_display_summary():
    assert "AI" in topic_display_summary("AI, 大模型")
