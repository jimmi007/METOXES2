import unittest,sys,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from metoxes.services.imported_score_service import discount_from_high
from metoxes.services.investing_import_service import attach_saved_lists

class ScoreDisplayTests(unittest.TestCase):
 def test_discount_uses_high_not_low_or_fair_value(self):
  self.assertEqual(discount_from_high(80,100),20)
  self.assertEqual(discount_from_high(110,100),-10)
  self.assertIsNone(discount_from_high(80,0));self.assertIsNone(discount_from_high(None,100))
 def test_existing_project_score_exact_and_same_quote_pair(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'investing_saved_lists.json').write_text(json.dumps({'lists':[{'rows':[{'name':'Example Inc','source_url':'key'}]}]}))
   p={'generated_at':'2026-10-04','candidates':[{'symbol':'EX','name':'Example Inc','final_score':73.42,'current_price':70,'high_52w':100}],'stocks':[]}
   p=attach_saved_lists(p,d,{'saved_investing_quotes':{'key':{'symbol':'EX','current_price':80,'high_52w':100,'checked_at':'2026-10-04'}}})
   r=p['investing_saved_lists'][0]['rows'][0]
   self.assertEqual(r['final_score'],73.42);self.assertEqual(r['discount_from_52w_high_pct'],20)
 def test_unknown_score_not_replaced_with_upside(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'investing_saved_lists.json').write_text(json.dumps({'lists':[{'rows':[{'name':'Example','source_url':'key','fields':{'Upside':'+80%'}}]}]}))
   r=attach_saved_lists({'stocks':[],'candidates':[]},d,{})['investing_saved_lists'][0]['rows'][0]
   self.assertIsNone(r['final_score']);self.assertIsNone(r['discount_from_52w_high_pct'])

if __name__=='__main__':unittest.main()
