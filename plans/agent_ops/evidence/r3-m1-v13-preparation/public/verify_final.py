"""One fresh installed interpreter verifies final pins/origins and denied entries."""
from pathlib import Path
import hashlib,json,subprocess,time
S=Path(__file__).resolve().parent;B=S.parent;D=S/'draft';Q=S/'final-entry-gates';Q.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=json.loads((D/'m1-codex-campaign-proposal-v13.json').read_bytes())
sources={v['path']:v['sha256'] for v in p['execution_bundle']['files'].values()}
sources[str(D/'m1-codex-campaign-proposal-v13.json')]=sha(D/'m1-codex-campaign-proposal-v13.json')
assert all(sha(k)==v for k,v in sources.items())
code=r'''
import sys,json,hashlib,importlib
from pathlib import Path
D=Path(sys.argv[1]);Q=Path(sys.argv[2]);S=D.parent;B=S.parent
sys.path[:0]=[str(D/'controller'),str(D)]
p=json.loads((D/'m1-codex-campaign-proposal-v13.json').read_bytes())
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
assert Path(sys.prefix).resolve()==Path(p['package_pins']['python_prefix']).resolve()
from campaign_context import verify_adoption
adoption=verify_adoption(p)
for entry in p['package_pins']['files']:assert sha(entry['path'])==entry['sha256']
assert len(p['package_pins']['files'])==984
for package in p['package_pins']['packages'].values():assert sha(package['wheel'])==package['sha256']
dependency_manifest=B/'draft/installation/dependency-manifest.json'
assert sha(dependency_manifest)==p['base06_installation']['dependency_manifest_sha256']
dependencies=json.loads(dependency_manifest.read_bytes())
for relative,digest in dependencies['files'].items():assert sha(Path(dependencies['destination'])/relative)==digest
assert sha(p['paths']['codex_executable'])==p['native_selection']['fingerprint'].split(':')[1]
for entry in p['execution_bundle']['files'].values():assert sha(entry['path'])==entry['sha256']
assert len(p['execution_bundle']['files'])==47
assert b'\r' not in Path(p['base06_installation']['requirements']).read_bytes()
names=sorted({key[len('controller_'):] for key in p['execution_bundle']['files'] if key.startswith('controller_')}|{'campaign_context','publication','response_loss','okto_nexus','okto_nexus_connector','nexus_connector_core','okto_nexus.adapters.inbound.cli.work'})
origins={}
for name in names:
    module=importlib.import_module(name);path=Path(module.__file__).resolve()
    expected=Path(sys.prefix)/'Lib/site-packages' if name.startswith(('okto_nexus','nexus_connector_core')) else D
    assert path.is_relative_to(expected.resolve())
    origins[name]={'path':str(path),'sha256':sha(path)}
for key,pin in p['execution_bundle']['files'].items():
    if not key.startswith('root_driver_'):continue
    path=Path(pin['path']).resolve();sys.path.insert(0,str(path.parent));m=importlib.import_module(path.stem)
    assert Path(m.__file__).resolve()==path;origins[key]={'path':str(path),'sha256':sha(path)}
from controller import POLICY,ANCESTRY
from api_worker import EffectFence
from independent_journal import ReadOnly
import token_collector
assert POLICY==p['controller_preparation']['policy'] and POLICY['revision']==13 and POLICY['max_new_admissions']==4 and POLICY['carry_in_admissions']==8 and POLICY['carry_in_tokens']==111651 and POLICY['max_cumulative_admissions']==12 and POLICY['preventive_cumulative_tokens']==500000 and POLICY['operational_tolerance']==700000
assert ANCESTRY==p['controller_preparation']['ancestry']
assert EffectFence().threshold==500000
state=token_collector.initial_state();assert state['stop_at']==500000 and state['max_requests']==4
assert token_collector.restore(token_collector.checkpoint(state))==state
reader=ReadOnly(B);assert reader.budget==.25 and reader.initialization_budget==.25;reader.close()
recipe=json.loads(Path(p['execution_bundle']['files']['remote_canonical_recipe']['path']).read_bytes())
assert recipe['format']=='m1-v13-readonly-remote-recipe' and recipe['proposal_revision']==13
assert recipe['limits']['policy']==POLICY
executor=recipe['operator_bootstrap']['executor']
assert {k:executor[k] for k in ('path','sha256')}==p['execution_bundle']['files'][executor['key']]
assert not (S/'public').exists() and not (S/'private').exists()
assert not (D/'m1_v13_setup.py').exists()
(Q/'module-origins.json').write_text(json.dumps({'status':'PASS','origins':origins,'source_pins':47,'installed_product_pins':984,'adoption':adoption,'policy':POLICY,'no_effects':True},indent=2)+'\n',encoding='utf-8')
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',str(S/'test_successor_entries.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]))
'''
env=json.loads((B/'draft/installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
started=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen([p['package_pins']['python'],'-I','-B','-X','utf8','-c',code,str(D),str(Q)],cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    rc=child.wait()
proof={'exit_code':rc,'duration_seconds':time.monotonic()-started,'inputs_before':sources,'inputs_unchanged':all(sha(k)==v for k,v in sources.items()),'control_public_private_absent':not (S/'public').exists() and not (S/'private').exists(),'scope':'Fresh installed -I/-B origin/hash proof, adopted immutable history,47 runtime/dependency pins,984 installed payload pins and21 refusal entries. No service/task/provider/credential or product installer; no actual receipt.'}
(Q/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps({k:v for k,v in proof.items() if k!='inputs_before'}));raise SystemExit(rc)
