"""Build local replay storage from bundled candles without network access."""
from pathlib import Path
import subprocess,sys,json

def bootstrap(base):
 base=Path(base);dest=base/'data/minute-bundled-exchange';manifest=dest/'manifest.json'
 if manifest.exists():
  if json.loads(manifest.read_text()).get('status')!='complete':raise ValueError('Bundled import is incomplete; preserve it and resolve before restarting.')
  return
 if dest.exists():raise ValueError('Incomplete bundled import directory exists; refusing to overwrite it.')
 subprocess.run([sys.executable,str(base/'import_csv.py'),'--nq',str(base/'sample_data/NQ_1m.csv'),'--es',str(base/'sample_data/ES_1m.csv'),'--name','bundled-exchange'],check=True)
