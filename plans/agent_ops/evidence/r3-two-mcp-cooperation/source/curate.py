from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
report=root/'source-initial'
public=root/'public-final'
public.mkdir(exist_ok=True)
result=json.loads((report/'result.json').read_text())
assert result['returncode']==0 and result['inputs_unchanged'] and not result['distributed_module_changes']
assert len(result['cases'])==2 and all(x['status']=='passed' for x in result['cases'])
for name,sha in result['source_hashes_after'].items():
    assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==sha
cases=list(ET.parse(report/'tests.xml').iter('testcase'))
assert len(cases)==2 and all(c.find(k) is None for c in cases for k in ('failure','error','skipped'))
summary=dict(scope='DX08 canonical cooperation smoke through two existing clients and the real application facade',
    literal_plan_line=460,
    literal='Troca dirigida e handoff explicitamente consentido; resultado válido é a cadeia canônica observada.',
    source_passed=2,source_failed=0,source_skipped=0,first_source_attempt=True,
    static_preflight='JS function/const shadow caught by root and independent reviewer before any campaign; renamed unwrapEnvelope. No product correction or executed failure.',
    source_cases=result['cases'],source_inputs_unchanged=8,distributed_modules_unchanged=17,
    clients=[dict(name='@modelcontextprotocol/inspector',version='0.21.2',sdk='TypeScript1.29.0'),
             dict(name='FastMCP Client',version='2.14.7',sdk='Python1.30.0')],
    contracts=['Separate exchange/handoff reviews and consents; wrong or premature consent has no canonical effect',
        'Directed message plus correlated reply observed through canonical metadata',
        'Exact peer claim_epoch and non-null synthetic completion result verified in handoffs',
        'Facade reconstructed from real CooperationFiles checkpoints retains IDs/receipts and makes no extra productive calls',
        'Same agent/session identity set; execution binding set remains empty; zero runtime operations',
        'Both owned client processes exit0; Server canonical stop and closed listener asserted'],
    limits=['Windows process owner qualification only','Programmatic Inspector modules, not Inspector standalone CLI',
        'Application facade, not a new CLI credential-launcher campaign','No model/provider, personal credentials or native adapter',
        'Synthetic non-null handoff result, not useful model work or M1','Reconstructed facade/checkpoints, not process crash during handoff',
        'Empty execution binding set proves no creation, not preservation of an existing managed binding'],
    credential_handling='Fixture keys/session secrets stay in private stdin and process memory. Private runtime homes, DBs and stderr excluded.',
    installed_result='Root performs separate installed qualification; this public bundle records source qualification only.',
    ledger_edits=0,product_changes=0,earlier_ac03_evidence_unchanged=True)
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
files={name:root/name for name in ['run_source.py','source-launcher.py','selectors.json',
    'distributed-module-inputs.json','curate.py','summary.json','source-initial/result.json',
    'source-initial/tests.xml','source-initial/stdout.log']}
for name in ['tests/execution_r4/test_two_existing_mcp_clients.py','tests/execution_r4/test_two_existing_mcp_cooperation.py']:
    files['source/'+name]=repo/name
for test_dir in sorted((report/'runtime').iterdir()):
    if not test_dir.is_dir() or test_dir.name.endswith('current'):
        continue
    for name in ('public-client-proof.json','public-cooperation-proof.json','owner-proofs.json'):
        path=test_dir/name
        if path.is_file():
            if name=='owner-proofs.json':
                owners=json.loads(path.read_text())
                assert len(owners)==1 and owners[0]['state']=='canonically_drained_owner_exited'
            files['proofs/'+test_dir.name+'/'+name]=path
assert sum(name.endswith('owner-proofs.json') for name in files)==2
assert sum(name.endswith('public-cooperation-proof.json') for name in files)==1
manifest=[]
for name,path in files.items():
    data=path.read_bytes()
    assert re.search(rb'nx'+rb's_[A-Za-z0-9_-]{16,}',data) is None
    destination=public/name
    assert destination.resolve().is_relative_to(public.resolve())
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(data)
    manifest.append(dict(path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
(public/'artifact-manifest.json').write_text(json.dumps(dict(public_allowlist=manifest,
    excluded=['runtime homes','DBs','private stderr','server logs','credentials','client dependency directories'],
    product_changes=0,ledger_edits=0),indent=2)+'\n',encoding='utf-8')
assert sorted(str(p.relative_to(public)).replace('\\','/') for p in public.rglob('*') if p.is_file())==sorted([*files,'artifact-manifest.json'])
print(json.dumps(dict(directory=str(public),files=len(manifest),
    manifest_sha256=hashlib.sha256((public/'artifact-manifest.json').read_bytes()).hexdigest())))
