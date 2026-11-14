"""Fresh isolated interpreter proves final import origins and all source pins; no campaign/test replay."""
from pathlib import Path
import hashlib,json,subprocess,time
R=Path(__file__).resolve().parent;D=R/'draft';Q=R/'final-composed-origins'
assert not Q.exists();Q.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=json.loads((D/'m1-codex-campaign-proposal-v11.json').read_bytes())
before={v['path']:v['sha256'] for v in p['execution_bundle']['files'].values()}
assert all(sha(path)==value for path,value in before.items())
env=json.loads((D/'installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
reference=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/venv')
code=r'''
import importlib,hashlib,json,sys
from pathlib import Path
D=Path(sys.argv[1]);Q=Path(sys.argv[2]);REF=Path(sys.argv[3]);p=json.loads((D/'m1-codex-campaign-proposal-v11.json').read_bytes())
sys.path[:0]=[str(D/'controller'),str(D)]
source_pins=p['execution_bundle']['files'];assert len(source_pins)==45
for pin in source_pins.values():assert hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()==pin['sha256']
names=sorted({key[len('controller_'):] for key in source_pins if key.startswith('controller_')}|{'publication','response_loss','campaign_context','okto_nexus','okto_nexus_connector','nexus_connector_core','okto_nexus.adapters.inbound.cli.work'})
origins={}
for name in names:
    module=importlib.import_module(name);path=Path(module.__file__).resolve()
    expected=REF/'Lib/site-packages' if name.startswith(('okto_nexus','nexus_connector_core')) else D
    assert path.is_relative_to(expected.resolve()),(name,path,expected)
    origins[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
for key,pin in source_pins.items():
    if not key.startswith('root_driver_'):continue
    path=Path(pin['path']).resolve();sys.path.insert(0,str(path.parent))
    module=importlib.import_module(path.stem);actual=Path(module.__file__).resolve()
    assert actual==path
    origins[key]={'path':str(actual),'sha256':hashlib.sha256(actual.read_bytes()).hexdigest()}
from controller import POLICY,ANCESTRY
from independent_journal import ReadOnly
assert POLICY==p['controller_preparation']['policy'] and POLICY['revision']==11 and POLICY['max_new_admissions']==5 and POLICY['carry_in_admissions']==6 and POLICY['carry_in_tokens']==89473 and POLICY['max_cumulative_admissions']==11
assert ANCESTRY==p['controller_preparation']['ancestry']
reader=ReadOnly(D.parent);assert reader.budget==.25 and reader.initialization_budget==.25;reader.close()
from cli_flow import cli
assert Path(cli.__file__).resolve().is_relative_to((REF/'Lib/site-packages').resolve())
assert not (D.parent/'campaign').exists()
(Q/'module-origins.json').write_bytes((json.dumps({'status':'PASS','modules':origins,'policy':POLICY,'ancestry':ANCESTRY,'source_pins_verified':len(source_pins),'read_ms':250,'initialization_ms':250,'provider_calls':0,'service_actions':0,'real_approval_created':False},indent=2)+'\n').encode())
'''
argv=[str(reference/'Scripts/python.exe'),'-I','-B','-X','utf8','-c',code,str(D),str(Q),str(reference)]
started=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    result=child.wait()
proof={'exit_code':result,'duration_seconds':time.monotonic()-started,'source_before':before,
    'source_unchanged':all(sha(path)==value for path,value in before.items()),'campaign_root_absent':not (R/'campaign').exists(),
    'scope':'Fresh -I -B process imports safe final controller/CLI/driver modules and verifies all45 source/dependency pins. Executable campaign entries are not imported; their missing-approval denials are tested separately. No real effects or repeated performance suite.'}
(Q/'result.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:proof[k] for k in ('exit_code','source_unchanged','campaign_root_absent','duration_seconds')}));raise SystemExit(result)
