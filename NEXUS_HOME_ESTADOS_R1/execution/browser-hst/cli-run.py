"""File-output transport for one explicitly named own Playwright CLI session."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--session',required=True)
p.add_argument('--log',required=True)
p.add_argument('--timeout',type=int,default=60)
p.add_argument('command',nargs=argparse.REMAINDER)
a=p.parse_args()
root=a.root.resolve()
assert root.name.startswith('nexus-hst-browser-') and a.session.startswith('hst-')
assert a.log and all(c.isalnum()or c in '-_' for c in a.log)
assert a.command and 1<=a.timeout<=90
path=root/('cli-'+a.log+'.txt');assert not path.exists(),'Preserve each antecedent'
with path.open('w',encoding='utf-8')as f:
    result=subprocess.run([r'C:/Program Files/nodejs/npx.cmd','--yes','--package','@playwright/cli','playwright-cli',
        '--session='+a.session,*a.command],stdout=f,stderr=subprocess.STDOUT,timeout=a.timeout)
print(json.dumps(dict(exit_code=result.returncode,log=str(path))))
text=path.read_text(encoding='utf-8')
print(text[:16000])
