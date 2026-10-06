import sys,unittest,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from metoxes.services.investing_import_service import parse_saved,normalized,attach_saved_lists

class ImportTests(unittest.TestCase):
 def test_actual_saved_list_counts_fields_and_unique(self):
  groups=json.loads((ROOT/'investing_saved_lists.json').read_text())['lists']
  self.assertEqual([len(g['rows']) for g in groups],[30,19])
  for g in groups:
   self.assertEqual(len({r['source_url'] for r in g['rows']}),len(g['rows']))
   for r in g['rows']:self.assertEqual(len(r['fields']),13)
  self.assertEqual(groups[1]['rows'][0]['fields']['Τιμή'],'24,860')
 def test_normalize_does_not_erase_greek(self):
  self.assertTrue(normalized('ΑΒΑΞ'));self.assertNotEqual(normalized('ΑΒΑΞ'),normalized('ΜΟΤΟΔΥΝΑΜΙΚΗ'))
 def test_masked_names_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.htm';p.write_text('<table><tr><th>Όνομα</th><th>Upside</th><th>Εύλογη αξία</th></tr><tr><td>Aaaaaa</td><td>10%</td><td>20</td></tr></table>')
   with self.assertRaises(ValueError):parse_saved(p,'United States','2026-10-04')
 def test_load_without_quotes_keeps_all_rows(self):
  p=attach_saved_lists({},ROOT,{})
  self.assertEqual(sum(len(g['rows']) for g in p['investing_saved_lists']),49)
  self.assertEqual(p['investing_saved_lists'][0]['rows'][0]['quote'],{})

if __name__=='__main__':unittest.main()
