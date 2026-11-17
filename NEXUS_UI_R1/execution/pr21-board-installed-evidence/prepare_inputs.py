from pathlib import Path
import hashlib
import json
import shutil
import tomllib

repo=Path(r'D:\Projetos\Techridy\okto_labs_okto_nexus')
root=Path(__file__).resolve().parent
mirror=root/'fixture-copy'
assert not mirror.exists();mirror.mkdir()
shutil.copytree(repo/'tests',mirror/'tests',ignore=shutil.ignore_patterns('__pycache__','*.pyc','.pytest_cache'))
for rel in ('NEXUS_UI_R1/execution/fixtures.py','NEXUS_UI_R1/execution/pr03-performance/measure.py','NEXUS_UI_R1/execution/pr09-offline-data-performance/run.py'):
    target=mirror/rel;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(repo/rel,target)
shutil.copytree(repo/'plans/contratos',mirror/'plans/contratos',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
markers=tomllib.loads((repo/'pyproject.toml').read_text())['tool']['pytest']['ini_options'].get('markers',[])
(mirror/'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\nmarkers=\n'+''.join('    '+m+'\n' for m in markers),encoding='utf-8')
assert not (mirror/'src').exists()
manifest={str(p.relative_to(mirror)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in mirror.rglob('*') if p.is_file()}
(root/'fixture-copy-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'mirror':str(mirror),'copied_files':len(manifest),'src_copied':False}))
