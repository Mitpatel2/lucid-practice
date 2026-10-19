import unittest,random
from session_dates import SessionDates
class RandomDates(unittest.TestCase):
 def dates(self):
  d=SessionDates('.')
  d.eligible=lambda *args:[('2026-10-12',{'dataset':'a','minutes':1}),('2026-10-12',{'dataset':'duplicate','minutes':1}),('2026-10-13',{'dataset':'a','minutes':5})]
  d.resolve=lambda local,dataset:{'local':local,'dataset':dataset}
  return d
 def test_random_day_time_bounds_and_resolution(self):
  d=self.dates();times=set();days=set()
  for seed in range(100):
   r=d.pick(rng=random.Random(seed),random_time=True);local=r['local'];hour,minute=map(int,local[11:].split(':'));n=hour*60+minute
   self.assertTrue(510<=n<=780);self.assertEqual(r['selection']['eligible_dates'],2)
   self.assertNotEqual(r['dataset'],'duplicate')
   if local[:10]=='2026-10-13':self.assertEqual(minute%5,0)
   times.add(local[11:]);days.add(local[:10])
  self.assertGreater(len(times),10);self.assertEqual(len(days),2)
 def test_legacy_day_only(self):self.assertTrue(self.dates().pick(rng=random.Random(1))['local'].endswith('08:30'))
 def test_empty(self):
  d=self.dates();d.eligible=lambda *args:[]
  with self.assertRaises(ValueError):d.pick(random_time=True)

 def test_synthetic_and_incomplete_excluded(self):
  d=SessionDates('.')
  d.index=lambda:{'first':'2026-10-12','latest':'2026-10-14','days':{'2026-10-12':[{'full':True,'minutes':1,'practice_eligible':False}], '2026-10-13':[{'full':False,'minutes':1}], '2026-10-14':[{'full':True,'minutes':1,'practice_eligible':True}]}}
  self.assertEqual([x[0] for x in d.eligible(resolution='1')],['2026-10-14'])
