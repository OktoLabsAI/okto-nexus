from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile,zipfile
import xml.etree.ElementTree as ET

base=Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr')
out=Path(tempfile.mkdtemp(prefix='r3-controls-installed-'))
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
python=base/'venv/Scripts/python.exe'
sources=[repo/'tests/test_service_process.py',repo.parent/'okto-nexus-connector/tests/integration/test_detached_service_lifecycle.py']
test_hashes={}
for p in sources:
    shutil.copy2(p,out/p.name)
    test_hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP'}}
for name in ('USERPROFILE','APPDATA','LOCALAPPDATA','HOME'):
    path=out/'profile'/name.lower()
    path.mkdir(parents=True,exist_ok=True)
    env[name]=str(path)
env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OKTO_NEXUS_NO_BANNER='1')
(out/'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n',encoding='utf-8')
proof={}
for w,module in [(base/'nexus-wheel-v1/okto_nexus-0.3.3-py3-none-any.whl','okto_nexus'),(repo/'vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl','okto_nexus_connector'),(repo/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl','nexus_connector_core')]:
    with zipfile.ZipFile(w) as z:
        names=[n for n in z.namelist() if n.startswith(module+'/') and not n.endswith('/')]
        assert all(z.read(n)==(base/'venv/Lib/site-packages'/n).read_bytes() for n in names)
        proof[module]={'wheel_sha256':hashlib.sha256(w.read_bytes()).hexdigest(),'files':len(names)}
command=[str(python),'-I','-X','utf8','-m','pytest','-c',str(out/'pytest.ini'),'--confcutdir='+str(out),*[str(out/p.name) for p in sources],'-v','--tb=short','--junitxml='+str(out/'tests.xml')]
(out/'environment.json').write_text(json.dumps({'forwarded_names':sorted(env),'isolated_profiles':True,'provider_credentials_forwarded':False,'native_task_registration':False},indent=2)+'\n')
(out/'package-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
with (out/'tests.txt').open('wb') as log:
    result=subprocess.run(command,cwd=out,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
cases=list(ET.parse(out/'tests.xml').iter('testcase')) if (out/'tests.xml').exists() else []
changed=[str(p) for p in sources if hashlib.sha256(p.read_bytes()).hexdigest()!=test_hashes[str(p)]]
summary={'exit':result.returncode,'command':command,'source_test_hashes':test_hashes,'changed_inputs':changed,'cases':len(cases),'failures':[c.attrib for c in cases if c.find('failure') is not None or c.find('error') is not None],'scope':'Actual disposable Windows detached CLI processes only. No provider/native user-task campaign.'}
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
(out/'run.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'out':str(out),**summary}))
raise SystemExit(result.returncode or bool(changed))
