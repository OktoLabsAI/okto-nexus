"""Run only after Root supplies final-assets.json; never run Vite here."""
from pathlib import Path
import hashlib, json, shutil, subprocess, zipfile

repo=Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
root=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
freeze=json.loads((root/'final-assets.json').read_text())
assert freeze['approved_by_root'] is True
backend={'src/okto_nexus/domain/home_entries.py': '8064505e83f783522a22a3a2a65827d2fd52b92d56e305c5f5339f7bfc1295cc', 'src/okto_nexus/domain/home_entry_pages.py': '473c8c199189e8d364468da7c11c1ea8d27a6259a71d0940461bee835d342f05', 'src/okto_nexus/domain/home_harness_board.py': 'e3714d2e3601a0a611baaf14dc4fea594c52ff7851944d4364f0b8ceaf3197d0', 'src/okto_nexus/domain/home_harness_blocking.py': 'f3fe6b223e4340d1a4cbdd93ee206459f60335c59b0da9a911d953790795b5ef', 'src/okto_nexus/application/home_entries.py': '35929e7a3c768b12dc43a99f8c8e4de5bb06bdea7ac64c34e9f0d64fb11caf8c', 'src/okto_nexus/application/home_ports.py': 'd451b14cb5806b423a6f202ba6293c32af41da8cb49c129d50eddac810d08748', 'src/okto_nexus/adapters/inbound/http/home_entries.py': '909bed37f0a311edcac0d7cc307cfb9bccc5f5701521754745f2968792da5e39', 'src/okto_nexus/adapters/outbound/sqlite/home_entries.py': 'a3a998518891893aeb541167af4b2f6f8e226090a7020fde3ae6a7a976674e20'}
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
old=Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r1-board-pr21-ei6yahi4/artifacts/okto_nexus-0.3.5-py3-none-any.whl')
wheel=root/'artifacts/okto_nexus-0.3.5-py3-none-any.whl'
with zipfile.ZipFile(old) as a, zipfile.ZipFile(wheel) as b:
    ns=lambda z:{n:z.read(n) for n in z.namelist() if n.startswith('okto_nexus/') and not n.endswith('/') and '/http/static/' not in n}
    x,y=ns(a),ns(b)
    changed=sorted(n for n in x.keys()&y.keys() if x[n]!=y[n])
    added=sorted(y.keys()-x.keys());removed=sorted(x.keys()-y.keys())
    assert added==['okto_nexus/domain/home_harness_blocking.py','okto_nexus/domain/home_harness_board.py'] and not removed
    assert changed==['okto_nexus/adapters/inbound/http/home_entries.py','okto_nexus/adapters/outbound/sqlite/home_entries.py','okto_nexus/application/home_entries.py','okto_nexus/application/home_ports.py','okto_nexus/domain/home_entries.py','okto_nexus/domain/home_entry_pages.py'],changed
report={'command':command,'exit_code':0,'source_sha256':pins,'source_drift':drift,'freeze':freeze,
 'comparison_to_PR21':{'nonstatic_before':len(x),'nonstatic_after':len(y),'changed':changed,'added':added,'removed':removed,'unchanged':sum(x[n]==y[n] for n in x.keys()&y.keys())},
 'artifacts':{p.name:sha(p) for p in (root/'artifacts').iterdir() if p.suffix in ('.whl','.gz')}}
(root/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'artifacts':report['artifacts'],'comparison':report['comparison_to_PR21']},indent=2))
