from pathlib import Path
import hashlib, json, socket, sys, tempfile, zipfile

REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
PROPOSAL=REPO/'plans/agent_ops/evidence/r3-m1-controller/m1-codex-campaign-proposal-v7.json'
p=json.loads(PROPOSAL.read_text())
root=Path(tempfile.mkdtemp(prefix='m1-execution-preflight-'))
assert sys.flags.isolated
import okto_nexus, okto_nexus_connector, nexus_connector_core
from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
from okto_nexus_connector.platform.user_service import UserService
proof={}
for name,module in [('nexus',okto_nexus),('connector',okto_nexus_connector),('core',nexus_connector_core)]:
    pin=p['package_pins'][name]
    package=Path(module.__file__).resolve().parent
    assert str(package).lower()==str(Path(pin['installed_import_path'])).lower()
    wheel=Path(pin['wheel'])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==pin['wheel_sha256']
    with zipfile.ZipFile(wheel) as z:
        expected={n.split('/',1)[1]:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith(module.__name__+'/') and not n.endswith('/')}
    actual={f.relative_to(package).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in package.rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.pyo')}
    assert actual==expected
    proof[name]={'files':len(actual),'wheel_sha256':pin['wheel_sha256'],'module_path':str(package)}
tasks={}
home=Path(p['paths']['server_home'])
for name,installation in [('nexus',ServerInstallation(home,home/'nexus.db')),('connector',UserService(Path(p['paths']['connector_state'])))]:
    assert installation.name==p['topology']['task_names'][name]
    observed=installation.tasks.read(installation.name)
    assert observed is None
    tasks[name]={'name':installation.name,'absent':True}
paths={k:{'path':v,'absent':not Path(v).exists()} for k,v in p['paths'].items() if k!='codex_executable'}
assert all(v['absent'] for v in paths.values())
with socket.socket() as s:
    s.bind(('127.0.0.1',64507))
native=Path(p['paths']['codex_executable'])
native_sha=hashlib.sha256(native.read_bytes()).hexdigest()
assert 'sha256:'+native_sha==p['native_selection']['fingerprint']
prepared=REPO/'plans/agent_ops/evidence/r3-m1-controller/preparation'
manifest=json.loads((prepared/'manifest.json').read_text())
for row in manifest['files']:
    f=prepared/row['path']
    assert hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256']
report={'status':'PASS_READ_ONLY_PREFLIGHT','proposal_sha256':hashlib.sha256(PROPOSAL.read_bytes()).hexdigest(),
        'packages':proof,'tasks':tasks,'paths':paths,'port':64507,'port_available':True,'native_sha256':native_sha,
        'controller_manifest_sha256':hashlib.sha256((prepared/'manifest.json').read_bytes()).hexdigest(),
        'provider_files_read':False,'provider_processes':0,'service_mutations':0,
        'authorization':'Root relayed explicit user execution approval for v7 on this turn.'}
(root/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'output':str(root/'preflight.json'),'status':report['status'],'packages':proof,'tasks':tasks,'port':64507}))
