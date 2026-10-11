"""Run from the project root: python -m pytest tests/test_dashboard_updates.py -q.

No network calls. JavaScript sorting checks need Node.js (otherwise skipped).
"""
import json
import shutil
import subprocess
import sys
import types
from copy import deepcopy
from datetime import date

import pytest
from metoxes.services import dashboard_service as service

AS_OF = date(2026, 10, 10)


def stock(**changes):
    row = dict(symbol='TEST', purchase_date='2026-08-01', market_value=1100,
               monthly_percent_change=10, purchase_price=50, quantity=10)
    row.update(changes)
    return row


def payload(stocks, day='2026-10-10'):
    return dict(generated_at=day+'T19:00:00', stocks=stocks,
                quarter_review=dict(cutoff='2026-07-10', recent={}, older={}))


@pytest.mark.parametrize('value,change,expected', [(1100, 10, 100), (900, -10, -100), (1000, 0, 0)])
def test_monthly_profit_uses_start_value_not_current_value(value, change, expected):
    result = service._monthly_profit_loss(stock(market_value=value, monthly_percent_change=change), AS_OF)
    assert result == pytest.approx(expected)


def test_recent_purchase_excludes_return_before_ownership():
    row = stock(purchase_date='2026-10-01', purchase_price=100, quantity=10,
                monthly_percent_change=50)
    assert service._monthly_profit_loss(row, AS_OF) == pytest.approx(100)


@pytest.mark.parametrize('bought,expected', [('2026-09-10', 600), ('2026-09-11', 600)])
def test_thirty_day_boundary(bought, expected):
    assert service._monthly_profit_loss(stock(purchase_date=bought), AS_OF) == pytest.approx(expected)


@pytest.mark.parametrize('changes', [
    {'purchase_date': None}, {'purchase_date': 'invalid'}, {'purchase_date': '2026-10-11'},
    {'market_value': None}, {'market_value': float('inf')},
    {'monthly_percent_change': None}, {'monthly_percent_change': float('nan')},
    {'monthly_percent_change': -100}, {'monthly_percent_change': -110},
    {'purchase_date': '2026-10-01', 'quantity': None},
])
def test_unavailable_profit_is_not_zero(changes):
    assert service._monthly_profit_loss(stock(**changes), AS_OF) is None


def test_cohorts_and_partial_coverage(tmp_path):
    data = payload([stock(purchase_date='2026-07-10'),
                    stock(purchase_date='2026-07-09', market_value=900, monthly_percent_change=-10),
                    stock(monthly_percent_change=None), stock(purchase_date='2026-10-11')])
    service._attach_dashboard_updates(data, tmp_path/'data.json')
    review = data['quarter_review']
    assert len(review['profit_loss_rows']) == 2
    assert len(review['older_profit_loss_rows']) == 1
    assert review['recent']['monthly_profit_loss'] == pytest.approx(100)
    assert review['older']['monthly_profit_loss'] == pytest.approx(-100)
    assert review['recent']['monthly_profit_loss_covered'] == 1
    assert review['recent']['monthly_profit_loss_total'] == 2


def test_all_missing_cohort_has_no_total(tmp_path):
    data = payload([stock(monthly_percent_change=None)])
    service._attach_dashboard_updates(data, tmp_path/'data.json')
    assert data['quarter_review']['recent']['monthly_profit_loss'] is None


def test_history_seeds_previous_day_updates_same_day_and_survives_restart(tmp_path):
    path = tmp_path/'data.json'
    path.write_text(json.dumps(payload([stock(market_value=900)], '2026-10-09')))
    first = payload([stock(market_value=1100)])
    service._attach_dashboard_updates(first, path)
    second = payload([stock(market_value=1200)])
    service._attach_dashboard_updates(second, path)
    path.unlink()  # History remains durable independently of the current snapshot.
    third = payload([stock(market_value=1300)], '2026-10-11')
    service._attach_dashboard_updates(third, path)
    assert third['portfolio_value_history'] == [
        {'date': '2026-10-11', 'value': 1300},
        {'date': '2026-10-10', 'value': 1200},
        {'date': '2026-10-09', 'value': 900}]
    saved = json.loads((tmp_path/'data_value_history.json').read_text())
    assert saved == third['portfolio_value_history']


def test_incomplete_valuation_does_not_overwrite_history(tmp_path):
    path = tmp_path/'data.json'
    good = payload([stock()])
    service._attach_dashboard_updates(good, path)
    incomplete = payload([stock(), stock(market_value=None)])
    service._attach_dashboard_updates(incomplete, path)
    assert incomplete['portfolio_value_history'] == good['portfolio_value_history']


@pytest.fixture
def offline_services(monkeypatch):
    from metoxes.services import portfolio_review_service as review
    def enrich(data, root):
        data['quarter_review'] = dict(cutoff='2026-07-10', recent={}, older={})
        return data
    monkeypatch.setattr(review, "enrich_payload", enrich)
    backtest = types.ModuleType('metoxes.services.model_backtest_service')
    backtest.load_latest_backtest_report = lambda: {}
    monkeypatch.setitem(sys.modules, review.__name__, review)
    monkeypatch.setitem(sys.modules, backtest.__name__, backtest)


def test_generate_writes_matching_json_html_and_history(tmp_path, offline_services):
    path, html = tmp_path/'data.json', tmp_path/'dashboard.html'
    stocks = [stock(name='</script><script>alert(1)</script>', relative_score=25)]
    original = deepcopy(stocks)
    result = service.generate_portfolio_dashboard(stocks, candidates=[], json_path=path,
                                                  html_path=html, snapshot_at='2026-10-10T19:00:00')
    data = json.loads(path.read_text())
    content = html.read_text()
    embedded = content.split('const PAYLOAD=', 1)[1].split(';\n', 1)[0]
    assert json.loads(embedded) == data
    assert '</script><script>alert(1)</script>' not in embedded
    assert 'relative_score' not in data['stocks'][0]
    assert data['stocks'][0]['monthly_profit_loss'] == pytest.approx(100)
    assert result == {'json_file': path, 'html_file': html}
    assert stocks == original
    assert 'Κέρδος/ζημιά τελευταίου μήνα' in content
    assert 'valueHistory' in content


def test_candidate_refresh_preserves_valuation_timestamp(tmp_path, monkeypatch):
    path = tmp_path/'data.json'
    before = payload([stock()], '2026-10-09')
    path.write_text(json.dumps(before))
    monkeypatch.setattr(service, 'DASHBOARD_JSON_FILE', path)
    calls = []
    monkeypatch.setattr(service, 'generate_portfolio_dashboard', lambda **kw: calls.append(kw))
    service.refresh_dashboard_candidates(candidates=[])
    assert calls[0]['snapshot_at'] == before['generated_at']
    assert calls[0]['stocks'] == before['stocks']


def test_javascript_numeric_date_sorting_and_missing_values():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for JavaScript execution')
    template = service.HTML_TEMPLATE
    start = template.index('const detailFields=')
    end = template.index('function updateSortHeaders()', start)
    script = template[start:end] + r'''
const assert=require('node:assert/strict');
const rows=[{market_value:2},{market_value:null},{market_value:10}];
assert.deepEqual(sortDetailRows(rows).map(x=>x.market_value),[10,2,null]);
detailSort.direction=1;
assert.deepEqual(sortDetailRows(rows).map(x=>x.market_value),[2,10,null]);
assert.deepEqual(rows.map(x=>x.market_value),[2,null,10]);
const dates=[{purchase_date:'2026-10-01'},{purchase_date:''},{purchase_date:'2025-12-01'}];
detailSort={field:'purchase_date',direction:1};
assert.deepEqual(sortDetailRows(dates).map(x=>x.purchase_date),['2025-12-01','2026-10-01','']);
detailSort.direction=-1;
assert.deepEqual(sortDetailRows(dates).map(x=>x.purchase_date),['2026-10-01','2025-12-01','']);
'''
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_dashboard_javascript_initial_render(tmp_path, offline_services):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for JavaScript execution')
    html = tmp_path/'dashboard.html'
    service.generate_portfolio_dashboard([stock()], candidates=[], json_path=tmp_path/'data.json',
                                         html_path=html, snapshot_at='2026-10-10T19:00:00')
    script = html.read_text().split('<script>',1)[1].split('</script>',1)[0]
    harness = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements={};
function element(){const children={};return {value:'',innerHTML:'',textContent:'',
 addEventListener(){},setAttribute(){},querySelector(k){return children[k]??=(element());}};}
const heads=Array.from({length:18},element);
const document={getElementById:id=>elements[id]??=(element()),
 querySelectorAll:s=>s==='.detail th'?heads:[]};
const context={document,Intl,URL,console,Plotly:{react(){}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
assert.ok(elements.quarterReview.innerHTML.includes('Απόδοση LastMonth'));
assert.ok(elements.quarterReview.innerHTML.includes('Total return from PD'));
assert.ok(elements.quarterReview.innerHTML.includes('Μέση μηνιαία άνοδος'));
assert.ok(elements.tbody.innerHTML.includes('TEST'));
assert.ok(elements.valueHistory.innerHTML.includes('10/10/2026'));
'''
    path = tmp_path/'dashboard.js'
    path.write_text(script)
    result = subprocess.run([node,'-e',harness,str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
