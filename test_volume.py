import unittest
from engine import aggregate, forming_bar

class VolumeTests(unittest.TestCase):
 def test_volume_totals_and_causal_forming(self):
  bars=[dict(t=i*60,o=100,h=101,l=99,c=100,v=i+1) for i in range(241)]
  for minutes in (1,5,15,30,60,240):
   closed=aggregate(bars,minutes*60,minutes,base=60)
   self.assertEqual(closed[-1]['v'],sum(range(1,minutes+1)))
   if minutes>1:
    partial=forming_bar(bars,(minutes-1)*60,minutes,base=60)
    self.assertEqual(partial['v'],sum(range(1,minutes)))
    self.assertLess(partial['v'],closed[-1]['v'])
