import unittest,tempfile
from pathlib import Path
from import_csv import read
class ImportTests(unittest.TestCase):
 def test_valid_and_duplicate(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'input.csv';header='ts_event,open,high,low,close,volume\n';row='2026-01-05T14:30:00Z,100,101,99,100,5\n';p.write_text(header+row)
   self.assertEqual(read(p,'NQ')[0][1],1767623400)
   p.write_text(header+row+row)
   with self.assertRaisesRegex(ValueError,'duplicate'):read(p,'NQ')
 def test_bad_timezone_and_geometry(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'input.csv'
   for row in ['2026-01-05T14:30:00,100,101,99,100,5','2026-01-05T14:30:00Z,100,98,99,100,5']:
    p.write_text('ts_event,open,high,low,close,volume\n'+row+'\n')
    with self.assertRaises(ValueError):read(p,'NQ')
