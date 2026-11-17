"""Run only after Root supplies final-assets.json; never run Vite here."""
from pathlib import Path
import hashlib, json, shutil, subprocess, zipfile

repo=Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
root=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
freeze=json.loads((root/'final-assets.json').read_text())
assert freeze['approved_by_root'] is True
backend={'src/okto_nexus/domain/home_board.py':'f93443cdd9e8100ab7541667a14a97c4512d0dee3c1799a470690eb55e0a77f8',
 'src/okto_nexus/application/home_entries.py':'a0bc17868a16297b1c7f997a7d9fc3d43d6d465cc9dccd93448badc5bd4add91',
 'src/okto_nexus/adapters/inbound/http/home_entries.py':'ab0413e5b51f7bb3aea034ba9292f904ff978067b90e549276e3f6b1f21ae6d3'}
for name,pin in {**backend,**freeze['assets']}.items():assert sha(repo/name)==pin,name
source=root/'source';source.mkdir()
shutil.copytree(repo/'src',source/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.egg-info'))
for name in ('pyproject.toml','README.md','LICENSE'):shutil.copy2(repo/name,source/name)
pins={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}
command=['rtk','proxy','uv','build','--out-dir',str(root/'artifacts'),str(source)]
with (root/'build.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
assert result.returncode==0,result.returncode
drift=[n for n,pin in pins.items() if sha(repo/n)!=pin]
assert not drift,drift
old=Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r1-ux-pr18-shdpm58d/artifacts/okto_nexus-0.3.5-py3-none-any.whl')
wheel=root/'artifacts/okto_nexus-0.3.5-py3-none-any.whl'
with zipfile.ZipFile(old) as a, zipfile.ZipFile(wheel) as b:
    ns=lambda z:{n:z.read(n) for n in z.namelist() if n.startswith('okto_nexus/') and not n.endswith('/') and '/http/static/' not in n}
    x,y=ns(a),ns(b)
    changed=sorted(n for n in x.keys()&y.keys() if x[n]!=y[n])
    added=sorted(y.keys()-x.keys());removed=sorted(x.keys()-y.keys())
    assert added==['okto_nexus/domain/home_board.py'] and not removed
    assert changed==['okto_nexus/adapters/inbound/http/home_entries.py','okto_nexus/application/home_entries.py'],changed
report={'command':command,'exit_code':0,'source_sha256':pins,'source_drift':drift,'freeze':freeze,
 'comparison_to_PR18':{'nonstatic_before':len(x),'nonstatic_after':len(y),'changed':changed,'added':added,'removed':removed,'unchanged':sum(x[n]==y[n] for n in x.keys()&y.keys())},
 'artifacts':{p.name:sha(p) for p in (root/'artifacts').iterdir() if p.suffix in ('.whl','.gz')}}
(root/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'artifacts':report['artifacts'],'comparison':report['comparison_to_PR18']},indent=2))
