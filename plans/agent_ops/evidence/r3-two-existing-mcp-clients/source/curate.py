from pathlib import Path
import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=repo/'tests/execution_r4/test_two_existing_mcp_clients.py'
caps=json.loads((root/'local-capabilities.json').read_text())
assert all(hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['sha256'] for x in caps['inputs'])
source_strings={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(source.read_text()).body
    if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)}
assert (root/'inspector.mjs').read_text()==source_strings['INSPECTOR_DRIVER']
assert (root/'fastmcp.py').read_text()==source_strings['FASTMCP_DRIVER']
public=root/'public'
public.mkdir(exist_ok=True)
(public/'test_two_existing_mcp_clients.py').write_bytes(source.read_bytes())
for name in ('public-client-proof.json','owner-proofs.json'):
    paths=list((root/'source-final/runtime').rglob(name))
    assert len(paths)==1
    (public/name).write_bytes(paths[0].read_bytes())
owner=json.loads((public/'owner-proofs.json').read_text())
assert len(owner)==1 and owner[0]['state']=='canonically_drained_owner_exited'
reports={}
for folder in ('source-initial','source-final'):
    cases=list(ET.parse(root/folder/'tests.xml').iter('testcase'))
    assert len(cases)==1
    reports[folder]=dict(count=1,passed=sum(all(c.find(t) is None for t in ('failure','error','skipped')) for c in cases),
        skipped=sum(c.find('skipped') is not None for c in cases),seconds=cases[0].get('time'))
assert reports['source-final']['passed']==1 and reports['source-final']['skipped']==0
summary=dict(scope='Existing Inspector programmatic client + FastMCP Client against current source Server real TCP',
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),reports=reports,
    initial_failure='Test expected parent_message_id in inbox DTO. Production DTO omits it. Final test checks exact parent/autorship/workspace in canonical messages rows and exact reply delivery separately; no production change.',
    same_driver_bytes_as_import_probes=True,distributed_modules_unchanged=17,
    source_and_helper_unchanged_during_each_run=True,
    final_owned_server_canonically_stopped=True,final_listener_closed=True,
    installed_qualification='Root retains installed evidence separately at r3-cooperative-drain-09ucmgsr/nexus-two-existing-mcp-clients; this bundle contains source qualification only.',
    limits=['Windows owner helper','No Claude/Codex participation claim','No provider or native adapter',
            'No user vault/client launch chain','No completed handoff smoke','Not the standalone Inspector CLI'],
    checkout_files_owned=['tests/execution_r4/test_two_existing_mcp_clients.py'])
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
names=['proposal.json','dx08-next.json','selectors.json','probe.py','local-capabilities.json','run_source.py','run_source_final.py',
    'curate.py','summary.json','inspector.mjs','fastmcp.py','public/public-client-proof.json','public/owner-proofs.json',
    'public/test_two_existing_mcp_clients.py']
names += [f'{kind}.{suffix}.txt' for kind in ('node-version','python-version','inspector-help','inspector-import','fastmcp-import') for suffix in ('stdout','stderr')]
names += [f'{folder}/{name}' for folder in ('source-initial','source-final') for name in ('tests.xml','stdout.log','result.json')]
items=[]
for name in names:
    data=(root/name).read_bytes()
    # No bearer/session material is expected in these public files. Runtime homes,
    # databases and private stderr are excluded rather than recursively copied.
    assert re.search(rb'nx' + rb's_[A-Za-z0-9_-]{16,}', data) is None
    items.append(dict(path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
manifest=dict(public_allowlist=items,excluded=['source-*/runtime except the two explicitly copied public reports',
    'server logs','private stderr','homes','databases','credentials','client package directories'],
    personal_credentials_read=False,new_product_code=False)
(root/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
final=root/'public-final'
final.mkdir(exist_ok=True)
for name in names+['artifact-manifest.json']:
    destination=final/name
    assert destination.resolve().is_relative_to(final.resolve())
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes((root/name).read_bytes())
assert sorted(str(p.relative_to(final)).replace('\\','/') for p in final.rglob('*') if p.is_file())==sorted(names+['artifact-manifest.json'])
print(json.dumps(dict(summary=summary,manifest_sha256=hashlib.sha256((root/'artifact-manifest.json').read_bytes()).hexdigest(),public_files=len(items))))
