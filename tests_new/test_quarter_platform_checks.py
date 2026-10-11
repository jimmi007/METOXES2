from copy import deepcopy
from datetime import date
import json
import shutil
import subprocess

import pytest
from metoxes.services import portfolio_review_service as review
from metoxes.services import dashboard_service as dashboard

ASOF=date(2026,10,10)

def opened(**changes):
    return dict(dict(symbol='OPEN',platform='A',purchase_date='2026-10-01',purchase_price=100,
                     quantity=2,market_value=220,current_price=110,percent_change=999,monthly_percent_change=5),**changes)

def sold(**changes):
    return dict(opened(symbol='SOLD',sell_date='2026-10-05',total_profit_loss=40),**changes)

def sample():
    return review.build_review([opened(),opened(symbol='OTHER',platform='B',market_value=180),
        opened(symbol='OLD',platform='B',purchase_date='2025-01-01')],ASOF,
        sold_stocks=[sold(),sold(symbol='SOLD_ONLY',platform='C'),sold(symbol='OLD_SOLD',platform='B',purchase_date='2025-01-01')])

def test_platform_filters_all_rows_and_recomputes_amounts_rates_and_winners():
    q=sample()
    assert set(q['by_platform'])=={'A','B','C'}
    assert q['recent']['combined_profit_loss']==80
    a,b,c=[q['by_platform'][p] for p in 'ABC']
    assert a['recent']['combined_profit_loss']==60
    assert a['recent']['combined_return_pct']==15
    assert a['recent']['winning_purchase_pct']==100
    assert a['recent']['weighted_monthly_pct']==10
    assert b['recent']['combined_profit_loss']==-20
    assert b['recent']['winning_purchase_pct']==0
    assert b['older']['combined_profit_loss']==60
    assert c['recent']['monthly_profit_loss'] is None
    assert c['recent']['combined_profit_loss']==40
    for name,sub in q['by_platform'].items():
        assert all(r['platform']==name for k in ('rows','older_rows','sold_rows','older_sold_rows') for r in sub[k])
        assert sub['audit']['status']==('partial' if name=='B' else 'ok')


def test_known_sold_profit_with_missing_cost_reconciles_but_return_is_partial():
    q=review.build_review([opened()],ASOF,sold_stocks=[sold(purchase_price=None)])
    g=q['recent']
    assert g['open_profit_loss']==20
    assert g['sold_profit_loss']==40
    assert g['combined_profit_loss']==60
    assert g['combined_covered']==2
    assert g['combined_return_covered']==1
    assert g['combined_return_pct']==10
    assert q['sold_rows'][0]['realized_return_pct'] is None
    assert q['audit']['status']=='partial'
    assert not q['audit']['errors']


@pytest.mark.parametrize('changes',[{'market_value':None},{'purchase_price':None},{'quantity':float('nan')}])
def test_missing_open_inputs_are_visible_and_not_zero(changes):
    q=review.build_review([opened(**changes)],ASOF)
    assert q['rows'][0]['purchase_profit_loss'] is None
    assert q['rows'][0]['data_issues']
    assert q['recent']['combined_profit_loss'] is None
    assert q['audit']['status']=='partial'
    assert not q['audit']['errors']


def test_invalid_dates_visible_in_correct_platform_audit():
    q=review.build_review([opened(purchase_date=None)],ASOF,sold_stocks=[sold(platform='B',sell_date='2026-09-01')])
    assert len(q['audit']['issues'])==2
    assert len(q['by_platform']['A']['audit']['issues'])==1
    assert len(q['by_platform']['B']['audit']['issues'])==1
    assert not q['rows'] and not q['sold_rows']


@pytest.mark.parametrize('kind',['summary','row','period','sold','return'])
def test_audit_detects_deliberately_corrupted_calculations(kind):
    q=deepcopy(sample())
    if kind=='summary':q['recent']['monthly_profit_loss']+=1
    if kind=='row':q['rows'][0]['purchase_profit_loss']+=1
    if kind=='period':q['rows'][0]['monthly_period_start']='2026-09-01'
    if kind=='sold':q['sold_rows'][0]['realized_profit_loss']+=1000
    if kind=='return':q['recent']['combined_return_pct']=999
    result=review.audit_review(q)
    assert result['status']=='error'
    assert result['errors']


def test_ownership_window_and_purchase_result_have_distinct_expected_totals():
    q=review.build_review([opened(),opened(symbol='LONG',purchase_date='2026-08-01',market_value=240,monthly_percent_change=-20)],ASOF)
    assert q['rows'][0]['purchase_return_pct']!=999
    bysymbol={r['symbol']:r for r in q['rows']}
    assert bysymbol['OPEN']['monthly_period_start']=='2026-10-01'
    assert bysymbol['LONG']['monthly_period_start']=='2026-09-10'
    assert q['recent']['monthly_profit_loss']==pytest.approx(-40)
    assert q['recent']['combined_profit_loss']==60


def test_empty_review_and_missing_platform():
    empty=review.build_review([],ASOF)
    assert empty['audit']['status']=='ok'
    assert empty['recent']['monthly_profit_loss'] is None
    q=review.build_review([opened(platform=None)],ASOF)
    assert 'Χωρίς πλατφόρμα' in q['by_platform']
    assert q['audit']['status']=='partial'


def test_browser_platform_change_updates_cards_rows_and_reset(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js required')
    q=sample()
    src=dashboard.HTML_TEMPLATE
    fn=src[src.index('function renderQuarter('):src.index('\nfunction isoDate')]
    js='const PAYLOAD='+json.dumps({'quarter_review':q},ensure_ascii=False)+';\n'+r'''
const assert=require('node:assert/strict');
const target={innerHTML:''};const document={getElementById:()=>target};
const esc=x=>String(x??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const euro=new Intl.NumberFormat('el-GR',{style:'currency',currency:'EUR'});
const pct=x=>x==null?'—':Number(x).toFixed(2)+'%';const num=x=>String(x??'—');const cls=x=>x<0?'neg':'pos';const safeLink=()=>'';
'''+fn+r'''
renderQuarter();const initial=target.innerHTML;
assert.ok(initial.includes('quarterPlatform'));
renderQuarter('A');assert.ok(target.innerHTML.includes('60,00'));
assert.ok(!target.innerHTML.includes('<b>OTHER</b>'));
assert.ok(!target.innerHTML.includes('SOLD_ONLY'));
assert.ok(target.innerHTML.includes('value="A" selected'));
renderQuarter('B');assert.ok(target.innerHTML.includes('-20,00'));
assert.ok(target.innerHTML.includes('OLD_SOLD'));
assert.ok(!target.innerHTML.includes('<b>OPEN</b>'));
renderQuarter('C');assert.ok(target.innerHTML.includes('SOLD_ONLY'));
assert.ok(!target.innerHTML.includes('<b>OTHER</b>'));
renderQuarter();assert.equal(target.innerHTML,initial);
'''
    path=tmp_path/'filter.js';path.write_text(js)
    result=subprocess.run([node,str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('dates',[['2026-09-10','2026-10-11'],['2026-09-01','2026-10-09']])
def test_history_outside_requested_window_is_not_used(dates):
    q=review.build_review([opened(purchase_date='2026-09-08',monthly_percent_change=None)],ASOF,
        histories={'OPEN':{'as_of':str(ASOF),'last_month_price_pct':50,'last_month_price_dates':dates}})
    assert q['recent']['monthly_profit_loss'] is None
    assert q['audit']['status']=='partial'


def test_attached_snapshot_full_javascript_and_platform_totals(tmp_path):
    from pathlib import Path
    import re
    source=(Path(__file__).resolve().parents[1]/'dashboard.html').read_text()
    data=json.loads(re.search(r'const PAYLOAD\s*=\s*(\{.*?\});\s*\n',source,re.S).group(1))
    q=data['quarter_review']
    assert not review.audit_review(q)['errors']
    for cohort in ('recent','older'):
        for field in ('monthly_profit_loss','combined_profit_loss'):
            subtotal=sum(v[cohort][field] for v in q['by_platform'].values() if v[cohort][field] is not None)
            assert q[cohort][field]==pytest.approx(subtotal)
    node=shutil.which('node')
    if not node:pytest.skip('Node.js required')
    js=tmp_path/'snapshot.js';js.write_text(source.split('<script>',1)[1].split('</script>',1)[0])
    harness=r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements={};function element(){const children={};return {value:'',innerHTML:'',textContent:'',addEventListener(){},setAttribute(){},querySelector:k=>children[k]??=(element())};}
const document={getElementById:id=>elements[id]??=(element()),querySelectorAll:s=>s==='.detail th'?Array.from({length:18},element):[]};
const context={document,Intl,URL,console,Plotly:{react(){}}};vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
assert.ok(elements.quarterReview.innerHTML.includes('quarterPlatform'));
const initial=elements.quarterReview.innerHTML;
for(const name of ['Capital','Freedom24','Trading212']){
 vm.runInContext('renderQuarter('+JSON.stringify(name)+')',context);
 assert.ok(elements.quarterReview.innerHTML.includes('Επιλογή: '+name));
 assert.notEqual(elements.quarterReview.innerHTML,initial);
}
vm.runInContext('renderQuarter()',context);assert.equal(elements.quarterReview.innerHTML,initial);
'''
    result=subprocess.run([node,'-e',harness,str(js)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
