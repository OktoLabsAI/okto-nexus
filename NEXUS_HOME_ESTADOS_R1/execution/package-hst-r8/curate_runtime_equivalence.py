"""R7→R8 byte proof only. No R8 pytest/browser qualification is inferred."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'package-hst-r7'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


old=read(BASE/'evidence/payload-manifest.json')
new=read(HERE/'evidence/payload-manifest.json')
old_ready=read(BASE/'READY.json')
new_ready=read(HERE/'READY.json')
assert old_ready['prefix_frozen'] and new_ready['prefix_frozen']
old_site=Path(old_ready['python']).parent.parent/'Lib/site-packages'
new_site=Path(new_ready['python']).parent.parent/'Lib/site-packages'
counts={}
for module in old.keys()|new.keys():
    before={name:pin for name,pin in old[module].items() if module!='okto_nexus' or '/http/static/' not in name}
    after={name:pin for name,pin in new[module].items() if module!='okto_nexus' or '/http/static/' not in name}
    assert before==after, (module,'Nonstatic payload changed')
    for name,pin in before.items():
        a,b=old_site/name,new_site/name
        assert sha(a)==sha(b)==pin and a.read_bytes()==b.read_bytes(),name
    counts[module]=len(after)
assert sum(counts.values())==1024
for module,items in old.items():
    for name,pin in items.items():
        assert sha(old_site/name)==pin,('Frozen R7 payload drift',name)
old_static={name:pin for name,pin in old['okto_nexus'].items() if '/http/static/' in name}
new_static={name:pin for name,pin in new['okto_nexus'].items() if '/http/static/' in name}
delta={'added':sorted(new_static.keys()-old_static.keys()),'removed':sorted(old_static.keys()-new_static.keys()),
       'changed':sorted(name for name in old_static.keys()&new_static.keys() if old_static[name]!=new_static[name])}
assert all(name.endswith('.js') for name in delta['added']+delta['removed'])
assert all(name.endswith(('/index.html','.js')) for name in delta['changed'])
old_pins=read(BASE/'evidence/source-pins-before.json')
new_pins=read(HERE/'evidence/source-pins-before.json')
assert all(old_pins[name]==new_pins[name] for name in ('pyproject.toml','uv.lock'))
old_env,new_env=read(BASE/'qualification.json'),read(HERE/'qualification.json')
assert old_env['python_version']==new_env['python_version']
assert old_env['dependencies']==new_env['dependencies']
evidence=[]
for path,expected in ((BASE/'installed-qualification.json',326),
                       (HERE.parent/'installed-supplement-r7/qualification.json',7)):
    value=read(path)
    assert value['counts']['PASS']==expected
    assert all(value['counts'].get(name,0)==0 for name in ('FAIL','ERROR','SKIP','NOT_RUN'))
    evidence.append({'path':str(path),'sha256':sha(path),'counts':value['counts'],
                     'executed_on':'Frozen R7 wheel, not R8',
                     'scope':'Exact unchanged installed backend bytes only; original fixture/SQL/browser/native limits remain'})
report={'status':'PASS_R7_R8_RUNTIME_BYTE_EQUIVALENCE','baseline_ready':old_ready,'current_ready':new_ready,
        'runtime_nonstatic_files':counts,'total_runtime_nonstatic_files':sum(counts.values()),
        'comparison':'Raw file byte equality plus immutable manifest hashes for all1024 nonstatic module files',
        'frozen_r7_all_payload_files':sum(len(items) for items in old.values()),
        'static_delta':delta,'python_version_equal':True,'dependency_versions_equal':True,
        'packaging_and_lock_equal':['pyproject.toml','uv.lock'],
        'third_party_limit':'Version metadata equality; raw third-party dependency bytes not compared',
        'reusable_installed_evidence':evidence,'pytest_executed_on_r8':False,
        'source_321_reuse':'R7 source tests are antecedent evidence only; backend byte proof does not rerun them on R8',
        'browser_evidence_reused':False,'required_separate_evidence':'R8 compiled UI real-browser checks',
        'old_prefix_reinstalled':False,'provider_calls':0}
output=HERE/'runtime-equivalence-vs-r7.json'
assert not output.exists()
output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'files':counts,'total':sum(counts.values()),
                  'pytest_r8':False,'sha256':sha(output)}))
