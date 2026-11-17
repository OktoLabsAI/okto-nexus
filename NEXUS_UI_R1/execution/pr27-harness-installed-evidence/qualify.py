from pathlib import Path
import json, os, subprocess

root=Path(__file__).resolve().parent
repo=Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
python=root/'venv/Scripts/python.exe'
wheel=root/'final/artifacts/okto_nexus-0.3.5-py3-none-any.whl'
core=repo/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'
connector=repo/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl'
manifest=json.loads((root/'final/build-manifest.json').read_text())
assert manifest['exit_code']==0 and not manifest['source_drift']
env={k:v for k,v in os.environ.items() if k.upper() not in {'PYTHONPATH','PYTHONHOME'}
     and not k.upper().startswith(('OKTO_','NEXUS_','OPENAI_','ANTHROPIC_','CODEX_','CLAUDE_'))}
for key,name in [('HOME','home'),('USERPROFILE','home'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata')]:
    target=root/name;target.mkdir(exist_ok=True);env[key]=str(target)
commands=[]
def run(name,args,timeout=300):
    argv=['rtk','proxy',*map(str,args)]
    with (root/(name+'.log')).open('w',encoding='utf-8') as log:
        result=subprocess.run(argv,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
    commands.append({'name':name,'argv':argv,'exit_code':result.returncode})
    (root/'commands.json').write_text(json.dumps(commands,indent=2)+'\n',encoding='utf-8')
    print(name,result.returncode,flush=True)
    if result.returncode:raise SystemExit(result.returncode)
run('install',[python,'-I','-m','pip','--isolated','install','--find-links',repo/'vendor/wheels',str(wheel)+'[serve-lite,dev]',core,str(connector)+'[test]'])
run('ci-smoke',[python,'-I',repo/'tools/ci_installed.py','smoke','--wheel',wheel,'--output',root/'ci-smoke'],60)
run('audit',[python,'-I',root/'audit_installed.py'],60)
run('installed-focal',[python,'-I',root/'run_focal.py'],300)
run('twine',['uvx','twine','check',wheel,root/'final/artifacts/okto_nexus-0.3.5.tar.gz'],60)
print('QUALIFICATION_PASS',flush=True)
