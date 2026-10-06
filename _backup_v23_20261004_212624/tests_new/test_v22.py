import sys, unittest, tempfile, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from metoxes.services.extended_review_service import history_metrics, build_six_month_review, attach_extended
from metoxes.services.portfolio_review_service import enrich_payload

class V22Tests(unittest.TestCase):
 def history(self):
  points=[{'date':d,'close':p,'adjusted_close':p} for d,p in [('2026-07-03',100),('2026-08-04',110),('2026-09-04',99),('2026-10-02',118.8)]]
  return history_metrics(points,'2026-10-04')
 def test_compounded_vs_arithmetic_mean(self):
  h=self.history();self.assertEqual(h['monthly_returns'],[10,-10,20]);self.assertAlmostEqual(h['mean_monthly_3m_pct'],6.6667);self.assertEqual(h['total_3m_pct'],18.8)
  self.assertEqual(h['price_dates'][-1],'2026-10-02');self.assertAlmostEqual(h['mean_close_3m'],109.2667)
 def test_missing_anchor_and_no_future_lookahead(self):
  p=[{'date':'2026-10-05','close':100,'adjusted_close':100}]
  self.assertEqual(history_metrics(p,'2026-10-04')['status'],'insufficient_history')
 def test_cutoff_duplicates_stale_missing(self):
  rows=[{'symbol':'A','purchase_date':'2026-04-04'},{'symbol':'A','purchase_date':'2026-09-04'}, {'symbol':'B','purchase_date':'2026-04-03'},{'symbol':'C','purchase_date':'2026-05-01'},{'symbol':'D','purchase_date':'2026-10-05'}]
  h=self.history();q=build_six_month_review(rows,'2026-10-04',{'A':h,'B':dict(h,as_of='2026-10-03')})
  self.assertEqual(q['cutoff'],'2026-04-04');self.assertEqual(q['recent']['positions'],3);self.assertEqual(q['recent']['valid_monthly'],1)
  self.assertEqual(q['older']['valid_monthly'],0);self.assertIsNone(q['difference_pp']);self.assertEqual(q['excluded_date_symbols'],['D'])
 def test_investing_has_no_invented_score_or_beta(self):
  p={'generated_at':'2026-10-04','stocks':[],'candidates':[]}
  s={'us_list':{'checked_at':'2026-09-01','rows':[{'name':'Example','source_url':'https://example.org'}]}}
  q=attach_extended(p,{},s)['investing_us'];self.assertEqual(q['status'],'stale');self.assertIsNone(q['rows'][0]['final_score']);self.assertEqual(q['rows'][0]['quote_status'],'missing')
 def test_payload_json_contract(self):
  with tempfile.TemporaryDirectory() as d:
   p=enrich_payload({'generated_at':'2026-10-04','stocks':[],'candidates':[]},root=d,network=False)
   self.assertIn('six_month_review',p);self.assertEqual(p['investing_us']['status'],'not_synced');json.dumps(p,allow_nan=False)

if __name__=='__main__':unittest.main()
