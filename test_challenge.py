import unittest
from challenge import configure,update,day
from engine import timestamp
class Challenge(unittest.TestCase):
 def account(self,**changes):
  s=dict(initial=25000,balance=25000,clock=timestamp('2026-06-01T13:00:00Z'),trades=[],position=None,pending=None)
  c=dict(target=1250,drawdown=1000,daily_loss=0,consistency=50,lock_profit=100,mode='static',daily_basis='equity',denominator='net',phase='evaluation');c.update(changes);configure(s,c);return s
 def test_consistency_no_false_failure(self):
  s=self.account();s['balance']=26250;update(s,26250);self.assertEqual(s['challenge']['status'],'active')
  s['clock']+=86400;s['balance']=27500;update(s,27500);self.assertEqual(s['challenge']['status'],'passed')
 def test_eod_trails_and_locks(self):
  s=self.account(mode='eod');s['balance']=26200;update(s,26200);self.assertEqual(s['challenge']['floor'],24000)
  s['clock']+=86400;update(s,26200);self.assertEqual(s['challenge']['floor'],25100)
  s['balance']=25100;update(s,25100);self.assertEqual(s['challenge']['status'],'failed')
 def test_daily_equity_and_missing(self):
  s=self.account(daily_loss=100);update(s,24900);self.assertEqual(s['challenge']['status'],'failed')
  s=self.account();update(s,None);self.assertEqual(s['challenge']['status'],'unverified')
 def test_intra_peak_and_uncertainty(self):
  s=self.account(mode='intraday');update(s,25500);self.assertEqual(s['challenge']['floor'],24500)
  update(s,25500,True);self.assertEqual(s['challenge']['status'],'unverified')
 def test_rollover_dst(self):
  self.assertNotEqual(day(timestamp('2026-06-01T21:59:00Z')),day(timestamp('2026-06-01T22:00:00Z')))
  self.assertNotEqual(day(timestamp('2026-12-01T22:59:00Z')),day(timestamp('2026-12-01T23:00:00Z')))
 def test_pause_reset_and_min_days(self):
  s=self.account(daily_loss=100,daily_action='pause');s['balance']=24900;update(s,24900)
  self.assertIn('paused_day',s['challenge']);self.assertNotEqual(s['challenge']['status'],'failed')
  s['clock']+=86400;update(s,24900);self.assertNotIn('paused_day',s['challenge'])
  s=self.account(consistency=0,min_days=2);s['balance']=27000;update(s,27000);self.assertEqual(s['challenge']['status'],'active')
 def test_validation(self):
  with self.assertRaises(ValueError):self.account(drawdown=float('nan'))
  with self.assertRaises(ValueError):self.account(consistency=101)
if __name__=='__main__':unittest.main()
