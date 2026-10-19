"""Conservative release inventory: examines only files staged in this repository."""
import subprocess,re,json,sys
from pathlib import Path
root=Path(__file__).parent
paths=subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines()
issues=[]
patterns=[('private-key',r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),('AWS-key',r'AKIA[0-9A-Z]{16}'),('GitHub-token',r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),('API-token',r'sk-(?:ant-)?[A-Za-z0-9_-]{30,}'),('personal-path',r'/Users/[^/\s]+/'),('credential-assignment',r'''(?i)(?:api_key|password|secret|access_token)\s*[=:]\s*["'][^"'\s]{8,}["']''')]
for name in paths:
 p=root/name
 if p.is_symlink() or any(part in ('data','sessions','models','outputs','.git') for part in p.relative_to(root).parts) or p.name.startswith('.env') or (p.suffix in ('.csv','.sqlite','.db','.pem','.key','.zip','.mov','.png') and name not in ('sample_data/NQ_1m.csv','sample_data/ES_1m.csv')):issues.append({'file':name,'reason':'excluded file type or directory'});continue
 text=subprocess.check_output(['git','show',':'+name],cwd=root).decode('utf-8')
 # The scanner's own detection strings are not credentials.
 if name=='check_release.py':continue
 for label,pattern in patterns:
  if re.search(pattern,text):issues.append({'file':name,'reason':label})
print(json.dumps({'staged_files':len(paths),'findings':issues,'scope':'Pattern and path checks; not a guarantee against all secrets'},indent=2))
sys.exit(bool(issues))
