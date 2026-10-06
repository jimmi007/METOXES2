import sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metoxes.services.us_value_service import build_screen,UNIVERSE
NOW=datetime(2026,10,4,18,tzinfo=timezone.utc)

def sample():
    return {s:dict(symbol=s,name=s,sector='Technology',country='United States',currency='USD',quote_type='EQUITY',
        market_cap=10e9,current_price=50,forward_pe=10 if i==0 else 20,free_cash_flow=800e6,profit_margin=.2,
        roe=.2,revenue_growth=.15,beta=0,low_52w=40,checked_at=NOW.isoformat()) for i,s in enumerate(UNIVERSE[:6])}

class ScreenTests(unittest.TestCase):
 def test_relative_valuation_and_holdings(self):
  q=build_screen({'us_value_quotes':sample()},['AAPL'],NOW)
  a=q['rows'][0];self.assertEqual(a['symbol'],'AAPL');self.assertEqual(a['peer_forward_pe'],20)
  self.assertEqual(a['pe_discount_pct'],50);self.assertEqual(a['value_score'],100)
  self.assertEqual(a['distance_from_52w_low_pct'],25);self.assertTrue(a['already_in_portfolio']);self.assertEqual(a['beta'],0)
 def test_missing_and_stale_not_scored(self):
  data=sample();data['AAPL']['free_cash_flow']=None
  data['MSFT']['checked_at']=(NOW-timedelta(hours=25)).isoformat()
  q=build_screen({'us_value_quotes':data},now=NOW)
  self.assertNotIn('AAPL',[r['symbol'] for r in q['rows']]);self.assertEqual(q['stale_count'],1)
 def test_no_sector_peers_no_score(self):
  q=build_screen({'us_value_quotes':dict(list(sample().items())[:4])},now=NOW);self.assertEqual(q['rows'],[])
 def test_losses_and_non_us_excluded(self):
  d=sample();d['AAPL']['profit_margin']=-.1;d['MSFT']['country']='Canada'
  q=build_screen({'us_value_quotes':d},now=NOW)
  self.assertNotIn('AAPL',[r['symbol'] for r in q['rows']]);self.assertNotIn('MSFT',[r['symbol'] for r in q['rows']])
 def test_no_data_and_future_timestamp(self):
  d=sample()
  for row in d.values():row['checked_at']=(NOW+timedelta(hours=1)).isoformat()
  q=build_screen({'us_value_quotes':d},now=NOW);self.assertEqual(q['status'],'unavailable');self.assertEqual(q['rows'],[])

if __name__=='__main__':unittest.main()
