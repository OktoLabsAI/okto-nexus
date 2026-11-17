from pathlib import Path
import subprocess, json, os, hashlib, zipfile, collections, sys

root = Path(__file__).resolve().parent
repo = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
python = root/'venv/Scripts/python.exe'
wheel = root/'artifacts/okto_nexus-0.3.5-py3-none-any.whl'
core = repo/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'
connector = repo/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl'
baseline = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r1-final-pr16-pxprmqxo/nexus/okto_nexus-0.3.5-py3-none-any.whl')
env = {k:v for k,v in os.environ.items() if k.upper() not in {'PYTHONPATH','PYTHONHOME'} and not k.upper().startswith(('OKTO_','NEXUS_','OPENAI_','ANTHROPIC_','CODEX_','CLAUDE_'))}
for key, folder in [('HOME','home'),('USERPROFILE','home'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata')]:
    target = root/folder; target.mkdir(exist_ok=True); env[key] = str(target)
commands=[]
def run(name, args):
    command=['rtk','proxy',*map(str,args)]
    result=subprocess.run(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (root/(name+'.log')).write_text(result.stdout,encoding='utf-8')
    commands.append({'name':name,'command':command,'exit_code':result.returncode})
    (root/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
    print(name,result.returncode,flush=True)
    if result.returncode: raise SystemExit(result.returncode)

with zipfile.ZipFile(wheel) as a, zipfile.ZipFile(baseline) as b:
    names=lambda z:{n for n in z.namelist() if n.startswith('okto_nexus/') and not n.endswith('/') and '/http/static/' not in n}
    assert names(a)==names(b) and len(names(a))==708
    assert all(a.read(n)==b.read(n) for n in names(a))
run('install',[python,'-I','-m','pip','install',str(wheel)+'[serve-lite]',core,connector,'packaging>=24'])
run('ci-smoke',[python,'-I',repo/'tools/ci_installed.py','smoke','--wheel',wheel,'--output',root/'ci-smoke'])
run('nexus-help',[root/'venv/Scripts/okto-nexus.exe','--help'])
run('connector-help',[root/'venv/Scripts/okto-nexus-connector.exe','--help'])
run('twine',['uvx','twine','check',wheel,root/'artifacts/okto_nexus-0.3.5.tar.gz'])
print('QUALIFIED',flush=True)
