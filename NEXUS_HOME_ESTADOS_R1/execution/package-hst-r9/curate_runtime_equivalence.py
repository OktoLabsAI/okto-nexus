"""Exact R8→R9 raw backend/dependency proof; no new pytest execution claim."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'package-hst-r8'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


old_ready,new_ready=read(BASE/'READY.json'),read(HERE/'READY.json')
assert old_ready['prefix_frozen'] and new_ready['prefix_frozen']
before,after=read(BASE/'evidence/payload-manifest.json'),read(HERE/'evidence/payload-manifest.json')
old_site=Path(old_ready['python']).parent.parent/'Lib/site-packages'
new_site=Path(new_ready['python']).parent.parent/'Lib/site-packages'
counts={}
for module in before.keys()|after.keys():
    a={key:value for key,value in before[module].items() if module!='okto_nexus' or '/http/static/' not in key}
    b={key:value for key,value in after[module].items() if module!='okto_nexus' or '/http/static/' not in key}
    assert a==b,('Nonstatic payload changed',module)
    for key,pin in a.items():
        assert sha(old_site/key)==sha(new_site/key)==pin,key
        assert (old_site/key).read_bytes()==(new_site/key).read_bytes(),key
    counts[module]=len(a)
assert counts=={'okto_nexus':729,'nexus_connector_core':168,'okto_nexus_connector':127}
for files in before.values():
    for key,pin in files.items():
        assert sha(old_site/key)==pin,('Frozen R8 payload drift',key)
a={key:pin for key,pin in before['okto_nexus'].items() if '/http/static/' in key}
b={key:pin for key,pin in after['okto_nexus'].items() if '/http/static/' in key}
delta={'added':sorted(b.keys()-a.keys()),'removed':sorted(a.keys()-b.keys()),
       'changed':sorted(key for key in a.keys()&b.keys() if a[key]!=b[key])}
assert all(key.endswith('.js') for key in delta['added']+delta['removed'])
assert all(key.endswith(('/index.html','.js')) for key in delta['changed'])
old_sources,new_sources=read(BASE/'evidence/source-pins-before.json'),read(HERE/'evidence/source-pins-before.json')
assert all(old_sources[name]==new_sources[name] for name in ('pyproject.toml','uv.lock'))
old_environment,new_environment=read(BASE/'qualification.json'),read(HERE/'qualification.json')
assert old_environment['python_version']==new_environment['python_version']
assert old_environment['dependencies']==new_environment['dependencies']
chain=read(BASE/'runtime-equivalence-vs-r7.json')
assert chain['status']=='PASS_R7_R8_RUNTIME_BYTE_EQUIVALENCE'
assert chain['total_runtime_nonstatic_files']==1024 and chain['pytest_executed_on_r8'] is False
assert chain['current_ready']==old_ready
refs=read(HERE/'baseline-evidence-refs.json')
for item in refs['references']:
    path=HERE.parent/item['path']
    assert sha(path)==item['sha256'],item['path']
    for artifact,pin in item.get('artifacts',{}).items():
        assert sha(HERE.parent/artifact)==pin,artifact
assert all(old_sources[name]==new_sources[name] for name in (
    'frontend/src/homeStatePresentation.ts','frontend/src/homeTypes.ts'))
report={'status':'PASS_R8_R9_RUNTIME_BYTE_EQUIVALENCE','baseline_ready':old_ready,'current_ready':new_ready,
    'runtime_nonstatic_files':counts,'total_runtime_nonstatic_files':sum(counts.values()),
    'frozen_r8_all_payload_files':sum(len(files) for files in before.values()),
    'raw_nonstatic_byte_equality':True,'static_delta':delta,
    'python_version_equal':True,'dependency_versions_equal':True,
    'packaging_and_lock_equal':['pyproject.toml','uv.lock'],
    'third_party_limit':'Third-party version metadata equality; raw byte proof covers Nexus/Core/Connector modules',
    'r8_to_r7_chain':{'path':str(BASE/'runtime-equivalence-vs-r7.json'),'sha256':sha(BASE/'runtime-equivalence-vs-r7.json'),
                     'reusable_installed_evidence':chain['reusable_installed_evidence']},
    'additional_baseline_references':refs,
    'unchanged_presentation_sources':['frontend/src/homeStatePresentation.ts','frontend/src/homeTypes.ts'],
    'presentation_layer_limit':'R8 source-copy TypeScript assertions remain that exact layer, not R9 bundle/browser execution',
    'pytest_executed_on_r9':False,'browser_evidence_reused':False,
    'scope':'Exact unchanged backend only; original source/fixture/platform/canonical-vs-synthetic limits remain',
    'required_separate_evidence':'R9 Node/build and real-browser verification for the changed pause/focus behavior',
    'provider_calls':0,'old_prefix_reinstalled':False}
output=HERE/'runtime-equivalence-vs-r8.json'
assert not output.exists()
output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'files':counts,'pytest_r9':False,'sha256':sha(output)}))
