import json,unittest
from pathlib import Path
from challenge import configure,update
from engine import Replay,timestamp
class Plans(unittest.TestCase):
 def account(self,**kw):
  s=dict(initial=50000,balance=50000,clock=timestamp('2026-10-12T14:00:00Z'),trades=[],position=None,pending=None)
  c=dict(target=3000,drawdown=2000,daily_loss=0,consistency=40,lock_profit=100,mode='static',daily_basis='equity',denominator='net',phase='evaluation',min_days=3);c.update(kw);configure(s,c);return s
 def advance(self,s,profit):
  s['trades'].append(dict(entry_at=s['clock']));s['balance']+=profit;update(s,s['balance']);s['clock']+=86400
 def test_target_alone_cannot_pass(self):
  s=self.account();self.advance(s,2000);self.advance(s,500);self.advance(s,500)
  a=s['challenge'];self.assertFalse(a['modeled_criteria_met']);self.assertAlmostEqual(a['consistency_pct'],2000/3000*100);self.assertEqual(a['remaining_target'],2000);self.assertNotEqual(a['status'],'failed')
  self.advance(s,1000);self.advance(s,1000);self.assertTrue(s['challenge']['modeled_criteria_met']);self.assertEqual(s['challenge']['status'],'passed')
 def test_loss_increases_consistency_requirement(self):
  s=self.account();self.advance(s,1000);self.advance(s,-500);a=s['challenge'];self.assertEqual(a['consistency_pct'],200);self.assertEqual(a['consistency_remaining'],2000)
 def test_none_zero_and_negative_denominator(self):
  s=self.account();self.assertIsNone(s['challenge']['consistency_pct']);self.advance(s,-100);self.assertIsNone(s['challenge']['consistency_pct']);self.assertFalse(s['challenge']['consistency_met'])
 def test_funded_never_passes(self):
  s=self.account(phase='funded',consistency=0);self.advance(s,5000);self.assertFalse(s['challenge']['modeled_criteria_met'])
 def test_all_catalog_configs_and_micro_only(self):
  rows=json.loads(Path('prop_catalog.json').read_text())['presets'];self.assertEqual(len(rows),len({r['id'] for r in rows}))
  for p in rows:
   with self.subTest(p=p['id']):
    s=self.account(**dict(p['config'],reference=p));self.assertEqual(s['challenge']['config']['consistency'],p['config']['consistency'])
    if p['config'].get('micro_only'):
     self.assertEqual(Replay.quantity_limit(None,s,'NQ'),0);self.assertEqual(Replay.quantity_limit(None,s,'MNQ'),p['config']['max_micro'])
