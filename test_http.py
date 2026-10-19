"""HTTP regression tests using bundled candles and temporary session storage."""
import unittest,tempfile,shutil,subprocess,sys,socket,time,json,urllib.request,urllib.error,uuid
from pathlib import Path
class HTTP(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  c.tmp=tempfile.TemporaryDirectory();c.base=Path(c.tmp.name);root=Path(__file__).parent
  for p in root.glob('*.py'):shutil.copy(p,c.base/p.name)
  shutil.copytree(root/'sample_data',c.base/'sample_data')
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  c.url=f'http://127.0.0.1:{port}';c.proc=subprocess.Popen([sys.executable,str(c.base/'server.py'),'--port',str(port)],stdout=subprocess.DEVNULL)
  for _ in range(100):
   try:c.req('meta');break
   except OSError:time.sleep(.05)
  else:raise RuntimeError('Server startup failed')
 @classmethod
 def tearDownClass(c):c.proc.terminate();c.proc.wait();c.tmp.cleanup()
 @classmethod
 def req(c,path,d=None,headers=None):
  req=urllib.request.Request(c.url+'/api/'+path,data=json.dumps(d).encode() if d is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
  try:
   with urllib.request.urlopen(req,timeout=10) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def new(self,date='2026-10-16T08:30'):
  code,x=self.req('new',dict(local_date=date,dataset='auto',execution_resolution='1',tf=1));self.assertEqual(code,200);return x
 def payload(self,x,**kw):return dict(id=x['session']['id'],revision=x['session']['revision'],request_id=uuid.uuid4().hex,tf=1,**kw)
 def test_next_day_preserves_and_rewinds(self):
  x=self.new('2026-10-12T10:00');before=x['session']
  code,y=self.req('next-day',self.payload(x));self.assertEqual(code,200)
  from datetime import datetime
  from zoneinfo import ZoneInfo
  opened=datetime.fromtimestamp(y['session']['clock'],ZoneInfo('America/Chicago'))
  self.assertEqual((opened.hour,opened.minute),(17,0))
  self.assertGreater(y['session']['clock'],before['clock']);self.assertEqual(y['session']['balance'],before['balance'])
  self.assertEqual(y['session']['trades'],before['trades'])
  code,z=self.req('rewind',self.payload(y));self.assertEqual(code,200)
  self.assertEqual(z['session']['clock'],before['clock']);self.assertEqual(z['session']['dataset'],before['dataset'])
 def test_next_day_pending_rejected(self):
  x=self.new('2026-10-12T10:00');_,x=self.req('quick-order',self.payload(x,instrument='MNQ',side=1,qty=1,brackets=True,stop_points=20,target_points=40))
  code,y=self.req('next-day',self.payload(x));self.assertEqual(code,400)
 def test_next_day_last_recording_rejected(self):
  x=self.new();code,y=self.req('next-day',self.payload(x));self.assertEqual(code,400)
 def test_duplicate_order_once(self):
  x=self.new();d=self.payload(x,instrument='MNQ',side=1,qty=1,brackets=True,stop_points=20,target_points=40)
  a,y=self.req('quick-order',d);b,z=self.req('quick-order',d);self.assertEqual((a,b),(200,200));self.assertEqual(z['session']['pending']['qty'],1);self.assertEqual(y['session']['revision'],z['session']['revision'])
 def test_stale_tab(self):
  x=self.new();self.req('step',self.payload(x));code,y=self.req('quick-order',self.payload(x,instrument='MNQ',side=1,qty=1,brackets=True,stop_points=20,target_points=40));self.assertEqual(code,409);self.assertIsNone(y['state']['session']['pending'])
 def test_invalid_mutation_rollback(self):
  x=self.new();code,_=self.req('risk-settings',self.payload(x,enforced=True,risk=-1,loss=500,max_micro=10));self.assertEqual(code,400)
  _,y=self.req('state?id='+x['session']['id']+'&tf=1');self.assertEqual(x['session'],y['session'])
 def test_external_origin(self):
  x=self.new();code,_=self.req('step',self.payload(x),{'Origin':'https://untrusted.example'});self.assertEqual(code,400)
 def test_private_files(self):
  for name in ['.env','server.py','sessions','data','sample_data/NQ_1m.csv']:
   try:urllib.request.urlopen(self.url+'/'+name);self.fail(name)
   except urllib.error.HTTPError as e:self.assertEqual(e.code,404)
 def test_archive_end(self):
  x=self.new('2026-10-16T15:59')
  for _ in range(3):_,x=self.req('step',self.payload(x))
  self.assertTrue(x['session']['ended']);self.assertEqual(x['session']['balance'],25000)
 def test_full_day_reconciliation(self):
  x=self.new()
  for _ in range(452):
   code,x=self.req('step',self.payload(x));self.assertEqual(code,200)
   if x['session']['ended']:break
  self.assertTrue(x['session']['ended']);self.assertEqual(x['session']['balance'],x['session']['initial']+sum(t['amount'] for t in x['session']['cash_ledger']))
 def test_corrupt_session(self):
  p=self.base/'sessions'/('a'*32+'.json');p.write_text('{broken');code,x=self.req('meta');self.assertEqual(code,200);self.assertTrue(x['session_warnings']);self.assertEqual(p.read_text(),'{broken')

 def test_journal_note_persistence_and_drawings(self):
  x=self.new();_,x=self.req('note',self.payload(x,notes='Plan: wait for confirmation. Review: exited early.',drawings=[{'symbol':'NQ','price':30000,'type':'level'}]))
  _,y=self.req('state?id='+x['session']['id']+'&tf=1')
  self.assertEqual(y['session']['notes'],'Plan: wait for confirmation. Review: exited early.')
  _,z=self.req('note',self.payload(y,notes='Revised review'))
  self.assertEqual(z['session']['drawings'],y['session']['drawings'])

 def test_rewind_restores_account_and_preserves_future(self):
  x=self.new();_,x=self.req('quick-order',self.payload(x,instrument='MNQ',side=1,qty=1,brackets=True,stop_points=20,target_points=40))
  before=x['session'];_,advanced=self.req('step',self.payload(x))
  self.assertGreater(advanced['session']['clock'],before['clock'])
  d=self.payload(advanced);code,back=self.req('rewind',d);self.assertEqual(code,200)
  for field in ('clock','balance','trades','pending','position','cash_ledger'):
   self.assertEqual(back['session'][field],before[field],field)
  self.assertEqual(back['session']['rewind_count'],1)
  archive=self.base/'sessions'/'.replay-history'/(back['session']['rewind_archives'][-1]+'.json')
  self.assertEqual(json.loads(archive.read_text())['balance'],advanced['session']['balance'])
  _,duplicate=self.req('rewind',d);self.assertEqual(duplicate['session']['revision'],back['session']['revision'])
  _,again=self.req('step',self.payload(back))
  for field in ('clock','balance','position','cash_ledger'):
   self.assertEqual(again['session'][field],advanced['session'][field],field)
 def test_rewind_start_rejected(self):
  x=self.new();code,_=self.req('rewind',self.payload(x));self.assertEqual(code,400)
  _,y=self.req('state?id='+x['session']['id']+'&tf=1');self.assertEqual(x['session'],y['session'])
 def test_random_create_records_choice(self):
  code,x=self.req('new',dict(random_start=True,random_from='2026-10-12',random_through='2026-10-16',execution_resolution='1',tf=1))
  self.assertEqual(code,200)
  c=x['session']['date_selection']['selection'];self.assertTrue(c['random_time']);self.assertTrue('08:30'<=c['chosen_time']<='13:00')
  self.assertTrue('2026-10-12'<=c['chosen_date']<='2026-10-16');self.assertEqual(x['session']['trades'],[])
 def test_random_empty_range_rejected(self):
  code,x=self.req('new',dict(random_start=True,random_from='2020-01-01',random_through='2020-01-02',execution_resolution='1',tf=1))
  self.assertEqual(code,400);self.assertIn('No complete',x['error'])
if __name__=='__main__':unittest.main()
