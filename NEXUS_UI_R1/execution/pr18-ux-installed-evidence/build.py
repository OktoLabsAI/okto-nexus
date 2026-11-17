from pathlib import Path
import hashlib
import json
import shutil
import subprocess

repo=Path(r'D:\Projetos\Techridy\okto_labs_okto_nexus')
root=Path(__file__).resolve().parent
source=root/'source';source.mkdir()
shutil.copytree(repo/'src',source/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.egg-info'))
for name in ('pyproject.toml','README.md','LICENSE'):shutil.copy2(repo/name,source/name)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={str(p.relative_to(source)).replace('\\','/'):sha(p) for p in source.rglob('*') if p.is_file()}
assert pins['src/okto_nexus/adapters/inbound/http/static/assets/index-CKlKNFgD.js']=='b3344814b6699b7ca1dd9b9e2cd9d9415ed44e5e476da9cac7f44200666966f3'
assert pins['src/okto_nexus/adapters/inbound/http/static/assets/index-BP1to-F2.css']=='6efb2b626483e4f1b0c0c5bd986040a898c49feb4403afb28f963a4fac7a9811'
command=['rtk','proxy','uv','build','--out-dir',str(root/'artifacts'),str(source)]
with (root/'build.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
assert result.returncode==0,result.returncode
drift=[name for name,value in pins.items() if sha(repo/name)!=value]
assert not drift,drift
head=subprocess.run(['rtk','proxy','git','rev-parse','HEAD'],cwd=repo,capture_output=True,text=True,check=True).stdout.strip()
report={'command':command,'exit_code':0,'head_at_build':head,'source_sha256':pins,'source_drift':drift,'static_source':'Exact Root frozen CKl/BP1 build copied; no Vite invocation or repo asset writes.',
'artifacts':{p.name:sha(p) for p in (root/'artifacts').iterdir() if p.suffix in ('.whl','.gz')}}
(root/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report['artifacts'],indent=2))
