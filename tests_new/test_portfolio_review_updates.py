"""Offline regression tests: owned periods, weights, news, and history retrieval."""
import json
import sys
import types
from datetime import date, datetime
from io import BytesIO

import pytest
from metoxes.services import portfolio_review_service as review
from metoxes.services import portfolio_review_worker as worker
from metoxes.services import extended_review_service as extended

ASOF = date(2026, 10, 10)


def row(**kw):
    r = dict(symbol='TEST', name='Test company', platform='Broker', purchase_date='2026-08-01',
             purchase_price=100, quantity=10, current_price=110, market_value=1100,
             percent_change=10, monthly_percent_change=10)
    return {**r, **kw}


def test_fifteen_day_holding_ignores_positive_prepurchase_month():
    r = row(purchase_date='2026-09-25', market_value=900, current_price=90, monthly_percent_change=20)
    result = review.holding_period_metrics(r, ASOF)
    assert result['monthly_profit_loss'] == -100
    assert result['holding_monthly_pct'] == pytest.approx(-10)
    assert result['monthly_period_start'] == '2026-09-25'


def test_long_holding_uses_only_last_month_not_since_purchase():
    r = row(purchase_price=30, monthly_percent_change=10)
    result = review.holding_period_metrics(r, ASOF)
    assert result['monthly_profit_loss'] == pytest.approx(100)
    assert result['monthly_period_start'] == '2026-09-10'


def test_weighted_percent_and_money_have_same_sign_despite_positive_simple_mean():
    data = review.build_review([
        row(symbol='SMALL', market_value=200, monthly_percent_change=100),
        row(symbol='LARGE', market_value=9000, monthly_percent_change=-10),
    ], ASOF)
    group = data['recent']
    assert group['mean_monthly_pct'] > 0
    assert group['monthly_profit_loss'] == pytest.approx(-900)
    assert group['weighted_monthly_pct'] == pytest.approx(-900/10100*100)


def test_old_and_new_cohorts_apply_same_owned_period_rule():
    data = review.build_review([row(symbol='NEW', purchase_date='2026-09-25', market_value=900),
                               row(symbol='OLD', purchase_date='2025-01-01', market_value=900,
                                   monthly_percent_change=-10)], ASOF)
    assert data['rows'][0]['holding_monthly_pct'] == pytest.approx(-10)
    assert data['older_rows'][0]['holding_monthly_pct'] == pytest.approx(-10)
    assert data['older']['monthly_profit_loss'] == pytest.approx(-100)
    assert data['difference_pp'] == pytest.approx(0)


def test_fresh_historical_month_replaces_broker_fallback_and_stale_does_not():
    hist = dict(as_of=str(ASOF), last_month_price_pct=25,
                last_month_price_dates=['2026-09-10', '2026-10-09'])
    fresh = review.holding_period_metrics(row(), ASOF, hist)
    assert fresh['monthly_profit_loss'] == pytest.approx(220)
    assert fresh['monthly_basis'] == 'historical_close'
    stale = review.holding_period_metrics(row(), ASOF, {**hist, 'as_of': '2026-09-01'})
    assert stale['monthly_profit_loss'] == pytest.approx(100)
    assert stale['monthly_basis'] == 'portfolio_1m_fallback'


def test_missing_monthly_data_does_not_count_as_zero_or_full_coverage():
    data = review.build_review([row(), row(symbol='MISSING', monthly_percent_change=None)], ASOF)
    assert data['recent']['monthly_profit_loss_covered'] == 1
    assert data['recent']['monthly_profit_loss_total'] == 2
    assert data['recent']['weighted_monthly_pct'] == pytest.approx(10)


@pytest.mark.parametrize('symbol,expected', [('PPC.GR','PPC.AT'),('PSN.US','PSN'),
                                             ('THEON.EU','THEON.AS'),('ASML.EU','ASML.AS'),
                                             ('VUAA.L','VUAA.L')])
def test_history_maps_broker_tickers_to_correct_exchange(symbol, expected):
    assert worker.provider_symbol(symbol) == expected


def points():
    return [{'date': d, 'close': c, 'adjusted_close': c}
            for d, c in [('2026-07-10',100),('2026-08-10',110),
                         ('2026-09-10',121),('2026-10-09',133.1)]]


def test_saturday_uses_friday_close_for_three_month_history():
    result = extended.history_metrics(points(), ASOF)
    assert result['status'] == 'available'
    assert result['monthly_returns'] == pytest.approx([10,10,10])
    assert result['price_dates'][-1] == '2026-10-09'


def test_fetch_keeps_valid_prices_if_currency_metadata_fails(monkeypatch):
    seen=[]
    class Frame:
        def iterrows(self):
            return iter((datetime.fromisoformat(p['date']),
                         {'Close':p['close'],'Adj Close':p['adjusted_close']}) for p in points())
    class Ticker:
        def __init__(self, symbol): seen.append(symbol)
        def history(self, **kw): return Frame()
        def get_history_metadata(self): raise RuntimeError('metadata unavailable')
    monkeypatch.setitem(sys.modules, 'yfinance', types.SimpleNamespace(Ticker=Ticker))
    result = worker.fetch_history('PPC.GR', ASOF)
    assert seen == ['PPC.AT']
    assert result['status'] == 'available'
    assert result['currency'] is None
    assert result['last_month_price_pct'] == pytest.approx(10)


def test_stale_history_stays_missing_and_displays_reason():
    result = extended.build_six_month_review([row()], ASOF,
               {'TEST': {'as_of':'2026-09-01','status':'available','mean_monthly_3m_pct':10}})
    assert result['rows'][0]['monthly_percent_change'] is None
    assert 'ενημερωθεί' in result['rows'][0]['history']['reason']


def test_targeted_news_filters_source_and_date(monkeypatch):
    xml=b'''<rss><channel>
    <item><title>Company earnings</title><link>https://news.google.com/story1</link><pubDate>Fri, 09 Oct 2026 12:00:00 GMT</pubDate><source url="https://www.reuters.com">Reuters</source></item>
    <item><title>Wrong site</title><link>https://news.google.com/story2</link><pubDate>Fri, 09 Oct 2026 12:00:00 GMT</pubDate><source url="https://example.com">Other</source></item>
    <item><title>Old news</title><link>https://news.google.com/story3</link><pubDate>Fri, 09 Jan 2026 12:00:00 GMT</pubDate><source url="https://www.reuters.com">Reuters</source></item>
    </channel></rss>'''
    requests=[]
    def fetch(req, **kw):
        requests.append(req.full_url)
        return BytesIO(xml)
    monkeypatch.setattr(worker.urllib.request, 'urlopen', fetch)
    articles = worker.fetch_company_news(row(), ASOF)
    assert len(articles) == 1
    assert articles[0]['source'] == 'reuters.com'
    assert articles[0]['evidence'] == 'headline_only'
    assert 'bloomberg.com' in requests[0]
    assert 'capital.gr' in requests[0]
    assert 'quantity' not in requests[0]


def test_enrichment_offline_uses_saved_history_without_external_calls(tmp_path):
    cache={'history_3m':{'TEST':{**extended.history_metrics(points(),ASOF),
                              'last_month_price_pct':10,'provider_symbol':'TEST'}}}
    (tmp_path/'v21_research_cache.json').write_text(json.dumps(cache))
    payload={'generated_at':'2026-10-10T19:00:00','stocks':[row()], 'candidates':[]}
    result=review.enrich_payload(payload,root=tmp_path,network=False)
    assert result['quarter_review']['recent']['weighted_monthly_pct'] == pytest.approx(10)
    assert result['six_month_review']['rows'][0]['history']['status'] == 'available'
