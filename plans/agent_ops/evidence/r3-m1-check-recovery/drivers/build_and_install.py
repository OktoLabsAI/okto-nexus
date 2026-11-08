from pathlib import Path
import shutil,subprocess,json,hashlib,os
R=Path(__file__).parent
REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
S=R/'source';W=R/'wheels';PY=R/'venv/Scripts/python.exe'
assert not S.exists() and not W.exists()
S.mkdir();W.mkdir()
for name in ('pyproject.toml','README.md','LICENSE','uv.lock'):
    shutil.copyfile(REPO/name,S/name)
ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.egg-info','node_modules','.pytest_cache','.ruff_cache','evidence')
for name in ('src','tests','tools','vendor','docs','frontend','.github','plans/r4_execution','plans/contratos'):
    if (REPO/name).exists():shutil.copytree(REPO/name,S/name,ignore=ignore)
inputs={p.relative_to(S).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in S.rglob('*') if p.is_file()}
(R/'snapshot-inputs.json').write_text(json.dumps(inputs,indent=2))
env=json.loads((R/'environment.json').read_text())
env.update(OKTO_NEXUS_EMBEDDING_MODE='off',OKTO_NEXUS_DISABLE_HARNESS_DISCOVERY='1')
def run(name,argv):
    with (R/(name+'.stdout')).open('xb') as out,(R/(name+'.stderr')).open('xb') as err:
        child=subprocess.Popen(argv,cwd=R,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        (R/(name+'-process.json')).write_text(json.dumps({'pid':child.pid,'argv':argv}))
        code=child.wait()
    assert code==0,(name,code)
run('build',[str(PY),'-I','-m','pip','--isolated','wheel','--no-index','--no-deps','--no-build-isolation','--wheel-dir',str(W),str(S)])
wheel=next(W.glob('okto_nexus-*.whl'))
deps=json.loads((S/'vendor/ci/manifest.json').read_text())['artifacts']
products=[wheel]+[S/d['path'] for d in deps]
for d in deps:assert hashlib.sha256((S/d['path']).read_bytes()).hexdigest()==d['sha256']
req=R/'requirements-products.txt'
req.write_text(''.join(p.as_uri()+' --hash=sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()+'\n' for p in products))
run('install',[str(PY),'-I','-m','pip','--isolated','install','--no-index','--no-deps','--require-hashes','-r',str(req)])
run('pip-check',[str(PY),'-I','-m','pip','--isolated','check'])
record={'root':str(R),'source':str(S),'python':str(PY),'wheel':str(wheel),'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
        'source_snapshot_files':len(inputs),'products':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in products],
        'offline':True,'source_environments_modified':False,'provider':False,'native_service_actions':False}
(R/'build-install-result.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record))
