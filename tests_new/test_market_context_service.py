from metoxes.services.market_context_service import _sentiment


def test_simple_news_sentiment_signal():
    assert _sentiment([{"title": "Company beats estimates and raises guidance"}]) == "positive"
    assert _sentiment([{"title": "Company misses estimates and cuts guidance"}]) == "negative"
