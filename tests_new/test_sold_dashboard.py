from datetime import date
import pytest
from openpyxl import Workbook
from metoxes.services import dashboard_service as dashboard
from metoxes.services import portfolio_review_service as review

ASOF=date(2026,10,10)

def position(**kw):
    return dict(symbol='ABC',platform='Broker',purchase_date='2026-08-01',
                purchase_price=100,quantity=2,market_value=220,current_price=110,
                percent_change=10,monthly_percent_change=2,**kw)

def sale(**kw):
    return {**position(), 'sell_date':'2026-09-01','total_profit_loss':40,**kw}


def test_sold_changes_recent_totals_and_winning_fraction():
    data=review.build_review([position()],ASOF,sold_stocks=[sale(symbol='SOLD'),sale(symbol='LOSS',total_profit_loss=-20)])
    group=data['recent']
    assert group['total_purchases']==3
    assert group['winning_purchases']==2
    assert group['winning_purchase_pct']==pytest.approx(200/3)
    assert group['combined_profit_loss']==pytest.approx(40)
    assert group['combined_return_pct']==pytest.approx(40/600*100)
    assert len(data['sold_rows'])==2
    assert group['positions']==1  # LastMonth remains open positions only.


def test_purchase_date_not_sale_date_selects_cohort():
    data=review.build_review([],ASOF,sold_stocks=[sale(purchase_date='2025-01-01',sell_date='2026-10-01')])
    assert len(data['older_sold_rows'])==1
    assert not data['sold_rows']
    assert data['older']['combined_profit_loss']==40
    assert data['older']['combined_return_pct']==20


def test_partial_sale_counts_one_purchase_and_disjoint_costs():
    data=review.build_review([position()],ASOF,sold_stocks=[sale(quantity=1,total_profit_loss=-30)])
    group=data['recent']
    assert group['total_purchases']==1
    assert group['combined_profit_loss']==-10
    assert group['combined_return_pct']==pytest.approx(-10/300*100)
    assert group['winning_purchases']==0


def test_sold_uses_realized_profit_not_current_price():
    data=review.build_review([],ASOF,sold_stocks=[sale(current_price=999,percent_change=899)])
    sold=data['sold_rows'][0]
    assert sold['realized_profit_loss']==40
    assert sold['realized_return_pct']==20


def test_missing_sold_profit_is_unknown_and_stays_in_denominator():
    data=review.build_review([position()],ASOF,sold_stocks=[sale(symbol='UNKNOWN',total_profit_loss=None)])
    group=data['recent']
    assert group['winning_purchase_pct']==50
    assert group['unknown_purchases']==1
    assert group['combined_covered']==1
    assert data['sold_rows'][0]['realized_profit_loss'] is None


@pytest.mark.parametrize('changes',[{'sell_date':None},{'sell_date':'2026-10-11'},
                                      {'purchase_date':'2026-10-01','sell_date':'2026-09-01'}])
def test_invalid_or_future_sales_excluded(changes):
    data=review.build_review([],ASOF,sold_stocks=[sale(**changes)])
    assert data['excluded_sold_count']==1
    assert not data['sold_rows'] and not data['older_sold_rows']


def test_sold_excel_loader_skips_summary_and_preserves_dates(tmp_path,monkeypatch):
    path=tmp_path/'portfolio.xlsx'
    book=Workbook();sheet=book.active;sheet.title='Sold'
    sheet.append(['symbol','platform','purchase_date','sell_date','purchase_price','quantity','total_profit_loss'])
    sheet.append(['ABC','Broker',date(2026,8,1),date(2026,9,1),100,2,40])
    sheet.append(['TOTAL',None,None,None,None,None,40])
    book.save(path)
    monkeypatch.setattr(dashboard,'PORTFOLIO_EXCEL_FILE',path)
    rows=dashboard._load_sold_from_excel()
    assert len(rows)==1
    assert rows[0]['purchase_date'].startswith('2026-08-01')
    assert rows[0]['total_profit_loss']==40


def test_recent_cutoff_inclusive_and_breakeven_not_winner():
    data=review.build_review([],ASOF,sold_stocks=[sale(purchase_date='2026-07-10',total_profit_loss=0)])
    assert len(data['sold_rows'])==1
    assert data['recent']['winning_purchase_pct']==0
    assert data['recent']['combined_profit_loss']==0


def test_dashboard_template_displays_requested_four_sold_columns():
    template=dashboard.HTML_TEMPLATE
    assert '<th>Μετοχή</th><th>Ημ. απόκτησης</th><th>Total return from PD</th><th>Κέρδος/ζημιά</th>' in template
    assert 'Κερδισμένες αγορές από απόκτηση' in template
    assert 'winning_purchase_pct' in template


def test_attached_dashboard_has_no_undefined_payload_reference():
    from pathlib import Path
    html=Path(__file__).resolve().parents[1]/'dashboard.html'
    source=html.read_text(encoding='utf-8')
    assert 'quarterPlatform' in source
    assert 'renderSoldOverview();' not in source
    assert 'root.by_platform' in source
    assert 'auditHTML' in source
