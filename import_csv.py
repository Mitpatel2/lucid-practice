"""Import user-owned one-minute candles without network access."""
import argparse,csv,sqlite3,json,math,re,hashlib
from pathlib import Path
from datetime import datetime

def read(path,symbol):
 rows=[];seen=set()
 with path.open(newline='') as f:
  for line,r in enumerate(csv.DictReader(f),2):
   dt=datetime.fromisoformat(r['ts_event'].replace('Z','+00:00'))
   if dt.tzinfo is None:raise ValueError(f'{symbol} line {line}: timezone required')
   t=int(dt.timestamp());v=[float(r[k]) for k in ('open','high','low','close','volume')];o,h,l,c,vol=v
   if t%60 or dt.microsecond or not all(math.isfinite(x) for x in v) or not 0<l<=min(o,c)<=max(o,c)<=h or vol<0:raise ValueError(f'{symbol} line {line}: invalid one-minute candle')
   if t in seen:raise ValueError(f'{symbol} line {line}: duplicate timestamp')
   seen.add(t);rows.append((symbol,t,*v,r.get('contract') or symbol))
 if not rows:raise ValueError('Empty input')
 return sorted(rows,key=lambda r:r[1])
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--nq',type=Path,required=True);p.add_argument('--es',type=Path,required=True);p.add_argument('--name',required=True);a=p.parse_args()
 if not re.fullmatch('[a-z0-9][a-z0-9-]{0,48}',a.name):p.error('Use lowercase letters, digits and hyphens')
 rows=read(a.nq,'NQ')+read(a.es,'ES');dest=Path(__file__).parent/'data'/('minute-'+a.name);dest.mkdir(parents=True,exist_ok=False)
 with sqlite3.connect(dest/'minutes.sqlite') as db:
  db.execute('CREATE TABLE bars(symbol TEXT,t INTEGER,o REAL,h REAL,l REAL,c REAL,v REAL,contract TEXT,PRIMARY KEY(symbol,t))');db.executemany('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?)',rows)
 manifest={'status':'complete','resolution_seconds':60,'source_label':'Local CSV: '+a.name,'source':'User supplied; accuracy and licensing not independently verified','rows':len(rows),'sha256':{s:hashlib.sha256(p.read_bytes()).hexdigest() for s,p in [('NQ',a.nq),('ES',a.es)]}}
 (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Imported locally. Restart server and open Sessions. Existing datasets preserved.')
if __name__=='__main__':main()
