import unittest,tempfile,copy
from engine import Replay,aggregate,evidence

def bars():
 return [dict(t=1800000000+i*300,o=100.,h=101.,l=99.,c=100.,v=10.) for i in range(100)]
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.b=bars();self.r=Replay({'NQ':self.b,'ES':copy.deepcopy(self.b)},self.tmp.name)
  from datetime import datetime,timezone
  self.s=self.r.create(datetime.fromtimestamp(self.b[30]['t'],timezone.utc).isoformat())
 def tearDown(self):self.tmp.cleanup()
 def order(self,side=1):self.r.order(self.s,'MNQ',side,1,95 if side==1 else 105,110 if side==1 else 90)
 def test_failed_challenge_ends_and_freezes_clock(self):
  from challenge import configure
  configure(self.s,dict(phase='evaluation',target=1250,drawdown=1000,daily_loss=0,consistency=50,lock_profit=100,mode='static',daily_basis='equity',denominator='net',min_days=1,daily_action='pause'))
  self.s['balance']=23999
  self.r.step(self.s)
  self.assertTrue(self.s['ended']);clock=self.s['clock'];self.r.step(self.s);self.assertEqual(clock,self.s['clock'])
 def test_extreme_balance_rejected(self):
  from datetime import datetime,timezone
  date=datetime.fromtimestamp(self.b[30]['t'],timezone.utc).isoformat()
  with self.assertRaisesRegex(ValueError,'billion'):self.r.create(date,balance=2.5e20,risk=1e6,loss=1e7)
  self.s['initial']=2.5e20
  with self.assertRaisesRegex(ValueError,'billion'):self.order()
 def test_quick_pending_accumulation_and_cap(self):
  self.s['max_micro']=3
  for _ in range(3):self.r.quick_order(self.s,'MNQ',1,1,95,110)
  self.assertEqual(self.s['pending']['qty'],3)
  with self.assertRaises(ValueError):self.r.quick_order(self.s,'MNQ',1,1,95,110)
  self.assertEqual(self.s['pending']['qty'],3)
  self.r.quick_order(self.s,'MNQ',-1,1,105,90)
  self.assertEqual(self.s['pending']['qty'],2)
 def test_quick_scale_accumulates_and_nets(self):
  self.s['risk_enforced']=False;self.r.quick_order(self.s,'MNQ',1,1);self.r.step(self.s)
  for _ in range(3):self.r.quick_order(self.s,'MNQ',1,1)
  self.r.quick_order(self.s,'MNQ',-1,1)
  self.assertEqual(self.s['position']['scale_pending']['delta'],2)
  self.r.step(self.s);self.assertEqual(self.s['position']['qty'],3)
  self.r.quick_order(self.s,'MNQ',-1,3);self.r.step(self.s)
  self.assertIsNone(self.s['position'])
  self.assertAlmostEqual(self.s['balance'],self.s['initial']+sum(x['amount'] for x in self.s['cash_ledger']))
  self.assertIsNone(self.s['trades'][0]['realized_R'])
 def test_optional_brackets_and_add_stop(self):
  with self.assertRaisesRegex(ValueError,'warning only'):self.r.quick_order(self.s,'MNQ',1,1)
  self.s['risk_enforced']=False;self.r.quick_order(self.s,'MNQ',-1,1);self.r.step(self.s)
  self.assertIsNone(self.s['position']['stop']);self.assertIsNone(self.s['position']['target'])
  self.r.manage(self.s,stop=100.5);self.r.step(self.s)
  self.assertEqual(self.s['trades'][0]['reason'],'stop')
 def test_future_hidden(self):
  v=self.r.visible(self.s);self.assertTrue(all(b['t']+300<=self.s['clock'] for a in v['bars'].values() for b in a))
  before=copy.deepcopy(v);self.b[31]['h']=5000;self.assertEqual(before,self.r.visible(self.s))
 def test_aggregate_complete(self):
  t=self.b[0]['t'];self.assertEqual(len(aggregate(self.b,t+600,15)),0);self.assertEqual(len(aggregate(self.b,t+900,15)),1)
 def test_missing_bucket(self):self.assertEqual(aggregate([self.b[0],self.b[2]],self.b[0]['t']+900,15),[])
 def test_sync(self):
  self.r.step(self.s);v=self.r.visible(self.s);self.assertEqual(v['bars']['NQ'][-1]['t'],v['bars']['ES'][-1]['t'])
 def test_next_open_not_close(self):
  self.order();self.assertIsNone(self.s['position']);self.b[30].update(o=102,h=103,l=100,c=102);self.r.step(self.s);self.assertEqual(self.s['position']['entry'],102)
 def test_stop_first_ambiguous_and_cash(self):
  self.order();self.b[30].update(h=111,l=94);self.r.step(self.s);t=self.s['trades'][0];self.assertEqual(t['reason'],'ambiguous bar: stop first');self.assertAlmostEqual(t['net'],-11.54);self.assertAlmostEqual(self.s['balance'],25000+t['net'])
 def test_short(self):
  self.order(-1);self.b[30].update(l=89);self.r.step(self.s);self.assertAlmostEqual(self.s['trades'][0]['net'],18.46)
 def test_risk_rejection(self):
  with self.assertRaises(ValueError):self.r.order(self.s,'NQ',1,10,95,110)
 def test_gap_entry_rechecked(self):
  self.order();self.b[30].update(o=111,h=112,l=110,c=111);self.r.step(self.s);self.assertIsNone(self.s['position']);self.assertEqual(len(self.s['trades']),0)
 def test_gap_stop_overrun(self):
  self.order();self.r.step(self.s);self.b[31].update(o=90,h=92,l=89,c=91);self.r.step(self.s);self.assertTrue(self.s['trades'][0]['risk_overrun'])
 def test_review_fixed_before_future(self):
  self.order();review=copy.deepcopy(self.s['pending']['entry_review']);self.b[31]['c']=10000;self.r.step(self.s);self.assertEqual(self.s['position']['entry_review'],review)
 def test_persist(self):
  self.order();self.assertEqual(self.s,self.r.get(self.s['id']))
 def test_missing_execution_halts(self):
  self.order();self.r.step(self.s);del self.r.maps['NQ'][self.s['clock']];self.r.step(self.s);self.assertTrue(self.s['ended']);self.assertIsNotNone(self.s['position']);self.assertEqual(self.s['trades'],[])
 def test_no_widen(self):
  self.order();self.r.step(self.s)
  with self.assertRaises(ValueError):self.r.manage(self.s,94)
  self.r.manage(self.s,96);self.assertEqual(self.s['position']['stop'],96)
 def test_flatten_next_open(self):
  self.order();self.r.step(self.s);self.r.manage(self.s,flatten=True);self.assertIsNotNone(self.s['position']);self.r.step(self.s);self.assertEqual(len(self.s['trades']),1)
 def test_latest_price_independent_timeframe(self):
  self.assertEqual(self.r.visible(self.s,5)['known_prices'],self.r.visible(self.s,240)['known_prices'])
  self.assertEqual(self.r.visible(self.s)['known_prices']['NQ']['price'],100.)
 def test_markers_same_bar(self):
  self.order();self.b[30].update(h=111,l=94);self.r.step(self.s)
  m=self.r.visible(self.s)['markers'];self.assertEqual([x['kind'] for x in m],['Entry','Exit'])
  self.assertEqual(m[0]['at'],m[1]['at']);self.assertNotEqual(m[0]['id'],m[1]['id'])
  self.assertEqual([x['kind'] for x in self.s['activity']],['Pending','Open','Closed'])
 def test_legacy_markers(self):
  self.order();self.b[30].update(h=111,l=94);self.r.step(self.s)
  del self.s['trades'][0]['id'];self.s.pop('activity');self.r.save(self.s)
  loaded=self.r.get(self.s['id']);self.assertEqual(len(self.r.visible(loaded)['markers']),2)
 def test_cancel_event(self):
  self.order();self.r.cancel(self.s);self.r.step(self.s)
  self.assertEqual(self.s['activity'][-1]['kind'],'Cancelled');self.assertEqual(self.s['trades'],[])
 def test_fill_rejection_event(self):
  self.order();self.b[30].update(o=111,h=112,l=110,c=111);self.r.step(self.s)
  e=self.s['activity'][-1];self.assertEqual(e['kind'],'Rejected');self.assertEqual(e['price'],111)
 def test_exact_five_minute_gap_step(self):
  self.r.timeline=self.r.timeline[:31]+self.r.timeline[40:]
  before=self.s['clock'];self.r.step(self.s);self.assertEqual(self.s['clock']-before,300)
 def test_draft_persist_no_fill(self):
  self.r.draft(self.s,dict(instrument='MNQ',side=1,qty=1,stop=95,target=110))
  loaded=self.r.get(self.s['id']);self.assertEqual(loaded['draft']['stop'],95);self.assertIsNone(loaded['pending'])
 def test_initial_risk_preserved_after_tightening(self):
  self.order();self.r.step(self.s);initial=self.s['position']['planned_risk'];self.r.manage(self.s,99.5)
  self.r.step(self.s);self.assertEqual(self.s['trades'][0]['planned_risk'],initial)
 def test_preview_not_change_target(self):
  self.order();self.r.step(self.s);self.r.manage(self.s,96)
  self.assertEqual(self.s['position']['target'],110);self.assertEqual(self.s['activity'][-1]['kind'],'Stop updated')
if __name__=='__main__':unittest.main()
