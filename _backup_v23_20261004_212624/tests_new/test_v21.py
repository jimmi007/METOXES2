import sys,json,tempfile,time,unittest,importlib.util
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'metoxes/services'))
from portfolio_review_service import build_review,months_before,enrich_payload,clean,beta_assessment
class ReviewTests(unittest.TestCase):
 def test_boundary_duplicate_and_missing(self):
  rows=[{'symbol':'A','purchase_date':'2026-07-04','monthly_percent_change':10},{'symbol':'A','purchase_date':'2026-07-05','monthly_percent_change':10},{'symbol':'B','purchase_date':'2026-07-03','monthly_percent_change':-2},{'symbol':'C','purchase_date':'2026-08-01','monthly_percent_change':None},{'symbol':'D','purchase_date':'2027-01-01','monthly_percent_change':100}]
  r=build_review(rows,'2026-10-04');self.assertEqual(r['recent']['positions'],3);self.assertEqual(r['recent']['valid_monthly'],1);self.assertEqual(r['difference_pp'],12);self.assertEqual(r['excluded_date_symbols'],['D'])
 def test_calendar(self):self.assertEqual(months_before(date(2026,5,31),3),date(2026,2,28))
 def test_unknown_and_stale_are_not_false(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'investing_membership.json').write_text(json.dumps({'candidates':{'A':{'matched':True,'checked_at':'2026-01-01'}}}))
   p=enrich_payload({'generated_at':'2026-10-04','stocks':[],'candidates':[{'symbol':'A'},{'symbol':'B','beta':0}]},root=d,network=False)
   self.assertIsNone(p['candidates'][0]['investing_undervalued']);self.assertEqual(p['candidates'][0]['investing_status'],'stale');self.assertEqual(p['candidates'][1]['beta'],0)
 def test_secrets(self):self.assertNotIn('secret',clean('url?apikey=secret&x=1'));self.assertNotIn('password',clean({'password':'secret'}))
 def test_hard_deadline(self):
  # A real deliberately stuck child validates the wall-clock cap without network.
  with tempfile.TemporaryDirectory() as d:
   target=Path(d,'portfolio_review_service.py');target.write_text((ROOT/'metoxes/services/portfolio_review_service.py').read_text())
   Path(d,'portfolio_review_worker.py').write_text('import time\ntime.sleep(60)\n')
   spec=importlib.util.spec_from_file_location('deadline_module',target);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   start=time.monotonic();m.enrich_payload({'generated_at':'2026-10-04','stocks':[],'candidates':[]},root=d,budget_seconds=.2)
   self.assertLess(time.monotonic()-start,4)
if __name__=='__main__':unittest.main()
