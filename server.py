import math,copy
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pathlib import Path
import json,threading,argparse,mimetypes,math,gzip
from engine import Replay,load_data,SOURCE
BASE=Path(__file__).parent
from session_dates import SessionDates
dates=SessionDates(BASE)
lock=threading.Lock()
recent_engines={}
def recent_catalog():return {}
def exchange_catalog():return {}
def broad_catalog():return {}
def additional_minute_catalog():
 return {p.parent.name:json.loads(p.read_text()) for p in sorted((BASE/'data').glob('minute-*/manifest.json')) if json.loads(p.read_text()).get('status')=='complete'}
def selected(session=None,dataset=None):
 key=(session or {}).get('dataset',dataset)
 if key=='legacy-5m':return replay
 if key not in additional_minute_catalog():raise ValueError('Import local NQ/ES CSV data before starting a replay.')
 if key not in recent_engines:
  from minute_store import MinuteReplay
  recent_engines[key]=MinuteReplay(BASE/'data'/key/'minutes.sqlite',BASE/'sessions')
 return recent_engines[key]

def session_catalog():
 sessions=[];warnings=[]
 for p in sorted(replay.store.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
  try:
   s=replay.get(p.stem)
   if s['id']!=p.stem or not all(isinstance(s[k],(int,float)) and not isinstance(s[k],bool) and math.isfinite(s[k]) for k in ('clock','balance')):
    raise ValueError('Invalid session metadata')
   sessions.append({'id':s['id'],'clock':s['clock'],'balance':s['balance']})
  except (ValueError,TypeError,KeyError,OSError):
   warnings.append('Could not read saved session '+p.name+'. The original file is preserved; other sessions remain available.')
 return sessions,warnings

def timeframe(value):
 if isinstance(value,bool) or str(value) not in ('1','5','15','30','60','240'):
  raise ValueError('Unsupported chart timeframe')
 return int(value)

class Handler(BaseHTTPRequestHandler):
 def setup(self):
  super().setup();self.connection.settimeout(15)
 def local_host(self):
  return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
 def respond(self,value,code=200):
  body=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
  encodings={}
  for item in self.headers.get('Accept-Encoding','').split(','):
   parts=item.strip().lower().split(';');quality=1.
   for parameter in parts[1:]:
    if parameter.strip().startswith('q='):
     try:quality=float(parameter.strip()[2:])
     except ValueError:quality=0.
   encodings[parts[0]]=quality
  compressed=len(body)>100000 and encodings.get('gzip',encodings.get('*',0))>0
  if compressed:body=gzip.compress(body,compresslevel=1,mtime=0)
  self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Vary','Accept-Encoding')
  if compressed:self.send_header('Content-Encoding','gzip')
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if not self.local_host():return self.respond({'error':'Localhost access only'},403)
  u=urlparse(self.path);q=parse_qs(u.query)
  try:
   with lock:
    if u.path=='/api/dates':return self.respond(dates.index())
    if u.path=='/api/resolve-date':return self.respond(dates.resolve(q['local'][0],q.get('dataset',['auto'])[0],q.get('resolution',['any'])[0]))
    if u.path=='/api/random-date':return self.respond(dates.pick(q.get('start',[''])[0],q.get('end',[''])[0],q.get('resolution',['any'])[0],q.get('flow',['false'])[0]=='true'))
    if u.path=='/api/meta':
     sessions,warnings=session_catalog()
     return self.respond({'data':manifest,'minute_data':globals().get('minute_manifest'),'recent_data':recent_catalog(),'additional_minute_data':additional_minute_catalog(),'exchange_data':exchange_catalog(),'broad_data':broad_catalog(),'flow_data':globals().get('flow_meta'),'sessions':sessions,'session_warnings':warnings})
    if u.path=='/api/state':
     session=replay.get(q['id'][0]);return self.respond(selected(session).visible(session,timeframe(q.get('tf',['5'])[0])))
   name='index.html' if u.path=='/' else u.path.lstrip('/')
   if name in ('index.html','styles.css','app.js','chart.js','trade.js','indicators.js','structure.js','prop_catalog.json'):
    self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'text/plain');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write((BASE/name).read_bytes());return
   self.respond({'error':'Not found'},404)
  except Exception as e:self.respond({'error':str(e)},400)
 def do_POST(self):
  if not self.local_host():return self.respond({'error':'Localhost access only'},403)
  try:
   if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):raise ValueError('Cross-origin request blocked')
   n=int(self.headers.get('Content-Length',0))
   if not 0<n<=100000:raise ValueError('Invalid request length')
   d=json.loads(self.rfile.read(n));action=self.path
   if not isinstance(d,dict):raise ValueError('Expected a JSON object')
   tf=timeframe(d.get('tf',5))
   if action=='/api/ui' and not isinstance(d.get('ui',{}),dict):raise ValueError('Invalid layout settings')
   if action=='/api/note' and 'drawings' in d and not isinstance(d['drawings'],list):raise ValueError('Invalid drawings')
   with lock:
    route=None
    if action=='/api/new' and d.get('random_start'):
     route=dates.pick(d.get('random_from',''),d.get('random_through',''),str(d.get('execution_resolution','1')),False,random_time=True)
     d['date_selection']=route['selection']
    elif action=='/api/new' and d.get('local_date'):route=dates.resolve(d['local_date'],d.get('dataset','auto'),d.get('execution_resolution','any'))
    if route:d['dataset']=route['dataset'];d['date']=route['date']
    r=selected(dataset=d.get('dataset')) if action=='/api/new' else selected(replay.get(d['id']))
    if action=='/api/new' and str(d.get('execution_resolution','any'))!='any':
     if str(d['execution_resolution']) not in {'1','5'} or int(d['execution_resolution'])*60!=r.base:raise ValueError('Requested execution resolution is unavailable in this source; no automatic downgrade')
    with r.transaction():
     if action=='/api/new':
      r=selected(dataset=d.get('dataset'));s=r.create(d['date'],*[float(d.get(k,v)) for k,v in [('balance',25000),('risk',125),('loss',500),('fee',.77),('slip',0)]])
      from challenge import configure
      configure(s,d.get('challenge'));s['date_selection']=dict(route or {},selection=d.get('date_selection'));r.save(s)
     else:
      s=replay.get(d['id']);r=selected(s);rid=d.get('request_id')
      if rid and rid in s['requests']:return self.respond(r.visible(s,tf))
      if d.get('revision',s['revision'])!=s['revision']:return self.respond({'error':'Session changed. Reloaded current state; try again.','state':r.visible(s,tf)},409)
      if action=='/api/step':
       before=copy.deepcopy(s);r.step(s)
       if s['clock']!=before['clock']:
        key=r.checkpoint(before);s['rewind_stack']=before.get('rewind_stack',[])+[key]
      elif action=='/api/next-day':
       from datetime import datetime
       from session_dates import TZ
       from challenge import update as update_challenge
       if s['ended']:raise ValueError('This attempt has ended. Review it or start a new attempt.')
       if s['position'] or s['pending'] or s.get('draft'):raise ValueError('Close the position and cancel pending orders or drafts first.')
       row=dates.next_session(s['clock'],r.base//60);before=copy.deepcopy(s)
       day=datetime.fromtimestamp(row['start'],TZ).strftime('%Y-%m-%d %H:%M %Z')
       update_challenge(s,s['balance'])
       if s.get('challenge',{}).get('status') in ('failed','passed','criteria_met_unverified'):raise ValueError('This challenge is complete; start a new attempt.')
       s['clock']=row['start'];s['dataset']=row['dataset'];s['base_seconds']=row['minutes']*60
       update_challenge(s,s['balance'])
       s['events'].append('Continued same account on '+day+'; skipped while flat')
       s['rewind_stack']=before.get('rewind_stack',[])+[r.checkpoint(before)]
      elif action=='/api/rewind':r.rewind(s)
      elif action in ('/api/order','/api/quick-order'):
       if not isinstance(d['qty'],int) or isinstance(d['qty'],bool):raise ValueError('Quantity must be an integer')
       if action=='/api/quick-order' and 'brackets' in d:
        d['stop']=d['target']=None
        if d['brackets']:
         sl,tp=float(d['stop_points']),float(d['target_points'])
         if not all(math.isfinite(n) and n>0 and abs(n*4-round(n*4))<1e-7 for n in (sl,tp)):raise ValueError('Invalid bracket distances')
         source='NQ' if d['instrument'].endswith('NQ') else 'ES'
         last=r.maps[source].get(s['clock']-r.base)
         if not last:raise ValueError('No fresh completed price')
         d['stop']=last['c']-d['side']*sl;d['target']=last['c']+d['side']*tp
       (r.quick_order if action=='/api/quick-order' else r.order)(s,d['instrument'],d['side'],d['qty'],float(d['stop']) if d.get('stop') is not None else None,float(d['target']) if d.get('target') is not None else None)
      elif action=='/api/risk-settings':r.risk_settings(s,d.get('enforced'),d.get('risk'),d.get('loss'),d.get('max_micro'))
      elif action=='/api/draft':r.draft(s,d.get('draft'))
      elif action=='/api/scale':r.scale(s,d.get('delta'))
      elif action=='/api/manage':r.manage(s,float(d['stop']) if 'stop' in d else None,d.get('flatten',False))
      elif action=='/api/note':s['notes']=str(d.get('notes',s['notes']))[:10000];s['drawings']=d.get('drawings',s['drawings'])[:100];r.save(s)
      elif action=='/api/trade-note':
       trade=next((t for t in s['trades'] if t['id']==d.get('trade_id')),None)
       if trade is None:raise ValueError('Completed trade not found')
       trade['trader_notes']=str(d.get('notes',''))[:10000];r.save(s)
      elif action=='/api/ui':s['ui']=d.get('ui',{});r.save(s)
      elif action=='/api/cancel':r.cancel(s)
      else:raise ValueError('Unknown action')
      s['revision']+=1
      if rid:s['requests']=(s['requests']+[rid])[-100:]
      r.save(s)
     result=selected(s).visible(s,tf)
     json.dumps(result,allow_nan=False)
    self.respond(result)
  except Exception as e:self.respond({'error':str(e)},400)
 def log_message(self,*args):pass
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8766);a=p.parse_args()
 from bootstrap_data import bootstrap
 bootstrap(BASE)
 manifest={};replay=Replay({'NQ':[],'ES':[]},BASE/'sessions')
 (BASE/'data').mkdir(exist_ok=True)
 print(f'Local practice: http://127.0.0.1:{a.port}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
