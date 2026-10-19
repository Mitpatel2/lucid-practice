"""Cached daily coverage and immutable-source date routing; no bar payloads in UI."""
import json,sqlite3,hashlib,random
from pathlib import Path
from datetime import datetime,time,timezone
from zoneinfo import ZoneInfo
TZ=ZoneInfo('America/Chicago')
class SessionDates:
 def __init__(self,base):self.base=Path(base).resolve();self.memo=None;self.signature=None
 def sources(self):
  out=[]
  for p in sorted((self.base/'data').glob('*/manifest.json')):
   m=json.loads(p.read_text());db=p.parent/('bars.sqlite' if p.parent.name.startswith('broad-') else 'minutes.sqlite')
   if m.get('status')!='complete' or not db.exists():continue
   name=p.parent.name;step=m.get('resolution_seconds',300)
   flow_name=m.get('flow_dataset') or ('tbbo-20261017-pilot' if name=='minute-20261017-owned' else None)
   flow=None
   if flow_name:
    fp=p.parent.parent/flow_name/'manifest.json'
    if fp.exists():
     f=json.loads(fp.read_text())
     if f.get('enabled_for_replay') and f.get('coverage_verified'):flow=[f['start_ns']//10**9,f['end_ns']//10**9]
   priority=0 if name.startswith('exchange-week-') else 1 if name.startswith('minute-') else 2 if name.startswith('yahoo-') else 3
   label='Exchange 1m + matched flow window' if priority==0 else 'Owned exchange 1m' if priority==1 else 'Yahoo continuous 1m · no flow' if priority==2 else 'Broad continuous 5m · no flow'
   if m.get('source_label'):label=m['source_label']
   practice_eligible=not (m.get('synthetic') or m.get('test_only') or 'synthetic' in name.lower())
   out.append(dict(practice_eligible=practice_eligible,id=name,path=str(db),step=step,flow=flow,priority=priority,label=label,stamp=[db.stat().st_size,db.stat().st_mtime_ns,p.stat().st_mtime_ns]))
  return sorted(out,key=lambda x:(x['priority'],x['id']))
 def index(self):
  sources=self.sources();sig=hashlib.sha256(('entry-ready-v3-random-fixtures'+json.dumps(sources,sort_keys=True)).encode()).hexdigest();cache=self.base/'data/session-date-index-v1.json'
  if self.signature==sig:return self.memo
  if cache.exists():
   x=json.loads(cache.read_text())
   if x.get('signature')==sig:self.memo=x;self.signature=sig;return x
  days={}
  for src in sources:
   db=sqlite3.connect('file:'+src['path']+'?mode=ro',uri=True);counts={}
   for (t,) in db.execute("SELECT n.t FROM bars n INNER JOIN bars e ON n.t=e.t AND e.symbol='ES' WHERE n.symbol='NQ' ORDER BY n.t"):
    dt=datetime.fromtimestamp(t,TZ)
    if dt.weekday()>4 or not time(8,30)<=dt.time()<time(15):continue
    key=dt.date().isoformat();r=counts.setdefault(key,{'n':0,'first':t,'last':t,'contiguous':True})
    if r['n'] and t-r['last']!=src['step']:r['contiguous']=False
    r['last']=t;r['n']+=1
   for date,r in counts.items():
    start=int(datetime.combine(datetime.fromisoformat(date).date(),time(8,30),TZ).timestamp())
    full=r['n']==23400//src['step'] and r['first']==start and r['last']+src['step']==start+23400 and r['contiguous']
    full=full and db.execute("SELECT COUNT(*) FROM bars WHERE symbol IN ('NQ','ES') AND t=?",(start-src['step'],)).fetchone()[0]==2
    flow=bool(src['flow'] and src['flow'][0]<=start and start+23400<=src['flow'][1])
    days.setdefault(date,[]).append({'dataset':src['id'],'start':start,'minutes':src['step']//60,'full':full,'bars':r['n'],'flow':flow,'practice_eligible':src['practice_eligible']})
   db.close()
  complete=[d for d,v in days.items() if any(r['full'] for r in v)]
  x={'signature':sig,'days':days,'first':min(days) if days else None,'latest':max(complete) if complete else None,'sources':[{k:v for k,v in s.items() if k not in ('path','stamp')} for s in sources]}
  cache.write_text(json.dumps(x,separators=(',',':')));self.memo=x;self.signature=sig;return x
 def local_timestamp(self,text):
  dt=datetime.fromisoformat(text)
  if dt.tzinfo is not None:raise ValueError('Enter a Chicago local date and time without an offset')
  aware=dt.replace(tzinfo=TZ)
  if datetime.fromtimestamp(aware.timestamp(),TZ).replace(tzinfo=None)!=dt:raise ValueError('That Chicago time does not exist because of daylight saving time')
  if aware.utcoffset()!=dt.replace(tzinfo=TZ,fold=1).utcoffset():raise ValueError('Ambiguous Chicago daylight-saving time; choose an unambiguous time')
  return int(aware.timestamp())
 def resolve(self,local,dataset='auto',resolution='any'):
  if str(resolution) not in ('any','1','5'):raise ValueError('Choose 1-minute or explicit 5-minute execution')
  t=self.local_timestamp(local)
  for s in self.sources():
   if dataset!='auto' and s['id']!=dataset:continue
   if str(resolution)!='any' and s['step']!=int(resolution)*60:continue
   if t%s['step']:continue
   db=sqlite3.connect('file:'+s['path']+'?mode=ro',uri=True)
   n=db.execute("SELECT COUNT(*) FROM bars WHERE symbol IN ('NQ','ES') AND t IN (?,?)",(t,t-s['step'])).fetchone()[0];db.close()
   if n!=4:continue
   flow=bool(s['flow'] and s['flow'][0]<=t-300 and t<=s['flow'][1])
   daily=next((r for r in self.index()['days'].get(local[:10],[]) if r['dataset']==s['id']),{})
   return {'regular_session_complete':daily.get('full',False),'dataset':s['id'],'date':datetime.fromtimestamp(t,timezone.utc).isoformat(),'local':local,'timestamp':t,'minutes':s['step']//60,'flow':flow,'label':s['label'],'note':'Matched flow window; individual trade evidence still validated at decision time.' if flow else 'Candles only at this date; no matched order flow.'}
  if str(resolution)=='1':raise ValueError('Genuine synchronized NQ/ES one-minute data is unavailable at this time/source. Choose another date or explicitly select 5-minute execution. No downgrade or synthetic candles were used.')
  raise ValueError('No synchronized NQ/ES coverage at this exact Chicago time. Try another available date; five-minute-only dates require a 5-minute boundary. No date was shifted.')
 def eligible(self,start='',end='',resolution='any',flow=False):
  idx=self.index();start=start or idx['first'];end=end or idx['latest']
  if not start or not end or start>end:raise ValueError('Choose an ordered start/end date range')
  return [(d,r) for d,rows in sorted(idx['days'].items()) if start<=d<=end for r in rows if r['full'] and r.get('practice_eligible',True) and (resolution=='any' or r['minutes']==int(resolution)) and (not flow or r['flow'])]
 def pick(self,start='',end='',resolution='any',flow=False,rng=None,random_time=False):
  rows=self.eligible(start,end,resolution,flow);by_day={}
  for d,r in rows:by_day.setdefault(d,r)
  if not by_day:raise ValueError('No complete regular sessions match this range/filter. Widen the dates or allow five-minute/no-flow sessions.')
  chooser=rng or random.SystemRandom();d=chooser.choice(list(by_day));r=by_day[d]
  minute=chooser.choice(list(range(8*60+30,13*60+1,r['minutes']))) if random_time else 8*60+30
  local=d+f'T{minute//60:02d}:{minute%60:02d}'
  result=self.resolve(local,r['dataset']);result['selection']={'kind':'random_complete_rth','start':start,'end':end,'resolution':resolution,'flow_required':flow,'eligible_dates':len(by_day),'chosen_date':d,'random_time':random_time,'chosen_time':local[11:],'time_window':'08:30–13:00 Chicago' if random_time else '08:30 Chicago'};return result

 def next_session(self,clock,resolution=1):
  """Next recorded 17:00 Chicago open; only timestamps, never future prices."""
  candidates=[]
  for src in self.sources():
   if not src['practice_eligible'] or src['step']!=int(resolution)*60:continue
   db=sqlite3.connect('file:'+src['path']+'?mode=ro',uri=True)
   try:
    for (t,) in db.execute("SELECT n.t FROM bars n JOIN bars e ON n.t=e.t AND e.symbol='ES' WHERE n.symbol='NQ' AND n.t>? ORDER BY n.t",(clock,)):
     dt=datetime.fromtimestamp(t,TZ)
     if dt.hour==17 and dt.minute==0 and dt.second==0 and dt.weekday() not in (4,5):
      candidates.append(dict(start=t,dataset=src['id'],minutes=src['step']//60));break
   finally:db.close()
  if not candidates:raise ValueError('No later 5 p.m. Chicago session open is recorded in the imported data. Import overnight NQ/ES candles to continue; the account has not changed.')
  return min(candidates,key=lambda row:row['start'])
