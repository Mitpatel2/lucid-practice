import unittest,tempfile
from engine import Replay
def bar(t,o=100,h=101,l=99,c=100,contract='ESH6'):
 return dict(t=t,o=o,h=h,l=l,c=c,v=10,contract=contract)
class Scaling(unittest.TestCase):
 def test_long_short_cash_and_snapshot(self):
  for side in (1,-1):
   with tempfile.TemporaryDirectory() as d:
    b=[bar(i*60,o=100,h=101,l=99,c=100) for i in range(12)]
    r=Replay({'NQ':b,'ES':b},d,60,'test');s=r.create('1970-01-01T00:01:00Z')
    r.order(s,'MNQ',side,1,100-side*10,100+side*20);r.step(s)
    original=s['position']['entry_review'].copy()
    r.scale(s,1);r.step(s);self.assertEqual(s['position']['qty'],2)
    r.scale(s,-1);r.step(s);self.assertEqual(s['position']['qty'],1)
    r.scale(s,-1);r.step(s);self.assertIsNone(s['position'])
    self.assertAlmostEqual(s['balance'],25000-3.08)
    self.assertAlmostEqual(s['initial']+sum(e['amount'] for e in s['cash_ledger']),s['balance'])
    self.assertAlmostEqual(s['trades'][0]['net'],-3.08)
    self.assertEqual(s['trades'][0]['entry_review'],original)
    self.assertEqual(r.get(s['id'])['balance'],s['balance'])
 def test_fill_risk_rejection(self):
  with tempfile.TemporaryDirectory() as d:
   b=[bar(i*60,o=100,h=101,l=99,c=100) for i in range(12)];b[2]=bar(120,o=120,h=121,l=119,c=120)
   r=Replay({'NQ':b,'ES':b},d,60,'test');s=r.create('1970-01-01T00:01:00Z',risk=50)
   r.order(s,'MNQ',1,1,90,140);r.step(s);r.scale(s,1);r.step(s)
   self.assertEqual(s['position']['qty'],1);self.assertEqual(s['activity'][-1]['kind'],'Scale rejected')
 def test_preset_contract_equivalence(self):
  from challenge import configure
  with tempfile.TemporaryDirectory() as d:
   b=[bar(i*60) for i in range(12)];r=Replay({'NQ':b,'ES':b},d,60,'test');s=r.create('1970-01-01T00:01:00Z')
   configure(s,dict(mode='static',drawdown=1000,phase='evaluation',daily_basis='equity',denominator='net',max_micro=20,micro_per_mini=10))
   self.assertEqual(r.quantity_limit(s,'MNQ'),20);self.assertEqual(r.quantity_limit(s,'NQ'),2)
 def test_duplicate_queue_and_cap(self):
  with tempfile.TemporaryDirectory() as d:
   b=[bar(i*60) for i in range(12)];r=Replay({'NQ':b,'ES':b},d,60,'test');s=r.create('1970-01-01T00:01:00Z')
   r.order(s,'MNQ',1,1,90,120);r.step(s)
   with self.assertRaises(ValueError):r.scale(s,10)
   r.scale(s,1)
   with self.assertRaises(ValueError):r.scale(s,1)
if __name__=='__main__':unittest.main()
