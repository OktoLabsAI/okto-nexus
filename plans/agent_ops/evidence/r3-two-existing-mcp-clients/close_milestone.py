from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil,sys

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
temp=Path('C:/Users/jpamb/AppData/Local/Temp')
root=temp/'r3-cooperative-drain-09ucmgsr'
installed=root/'nexus-two-existing-mcp-clients'
target=repo/'plans/agent_ops/evidence/r3-two-existing-mcp-clients'
assert len(sys.argv)==4, 'source public allowlist, exact installed test directory, review JSON required'
source_public,test_directory,review=map(Path,sys.argv[1:])
result=json.loads((installed/'result.json').read_text())
campaign=json.loads((installed/'canonical/campaign.json').read_text())
assert result['exit']==0 and result['cases']==1 and not result['failures'] and not result['skips']
assert campaign['status']=='PASS' and campaign['changed_inputs']==[]
assert (installed/'pip-check.txt').read_text().strip()=='No broken requirements found.'
proof=json.loads((test_directory/'public-client-proof.json').read_text())
owners=json.loads((test_directory/'owner-proofs.json').read_text())
assert len(owners)==1 and owners[0]['state']=='canonically_drained_owner_exited'
assert proof['reconnect_same_sessions'] and proof['identity_and_bindings_unchanged']
assert proof['runtime_operations']==proof['native_adapters_added']==0
assert len(proof['clients'])==len(proof['sessions'])==len(proof['message_ids'])==2
external=json.loads((installed/'external-client-proof.json').read_text())
assert external['unchanged_before_and_after'] and not external['full_transitive_lock_claim']
source_proof=json.loads((root/'two-mcp-source-proof.json').read_text())
assert hashlib.sha256((repo/source_proof['test']).read_bytes()).hexdigest()==source_proof['source_sha256']
assert (repo/source_proof['test']).read_bytes()==(root/'nexus-source-v1'/source_proof['test']).read_bytes()
source_manifest=json.loads((source_public/'artifact-manifest.json').read_text())
for entry in source_manifest['public_allowlist']:
    assert hashlib.sha256((source_public/entry['path']).read_bytes()).hexdigest()==entry['sha256']
assert not target.exists()
target.mkdir()
locations={}
def copy(source,relative):
    destination=target/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(source.read_bytes())
    locations[str(source)]=dict(published_path=destination.relative_to(repo).as_posix(),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
for p in source_public.rglob('*'):
    if p.is_file():copy(p,Path('source')/p.relative_to(source_public))
for p in installed.rglob('*'):
    if p.is_file() and p.suffix in {'.json','.xml','.txt'}:copy(p,Path('installed')/p.relative_to(installed))
for name in ('public-client-proof.json','owner-proofs.json'):copy(test_directory/name,Path('installed-observations')/name)
for name in ('qualify_two_mcp_clients.py','two-mcp-source-proof.json'):copy(root/name,name)
copy(temp/'prepare_two_mcp_clients_qualification.py','prepare_two_mcp_clients_qualification.py')
copy(review,'readonly-review.json')
copy(Path(__file__),'close_milestone.py')
(target/'evidence-location-map.json').write_text(json.dumps(locations,indent=2)+'\n')
prefix=target.relative_to(repo).as_posix()
summary='MCP Inspector0.21.2 programmatic distributed client (TypeScript SDK1.29.0) and FastMCP2.14.7 (Python SDK1.30.0) each establish useful sessions over real TCP, exchange and acknowledge a correlated directed request/reply, then reconnect without new identities or sessions. Actual installed Server exits canonically. No native adapter or model is involved.'
limits=['Inspector programmatic modules are qualified, not a claim that its CLI protects bearer argv.',
        'Credentials and profiles are synthetic; neither personal vault/launcher integration nor paid inference was exercised.',
        'No productive runtime bindings exist in this fixture: unchanged empty bindings prove no creation, not preservation of productive bindings.',
        'AC03 participation is qualified; DX08 separately consented handoff smoke and M1 are not inferred.',
        'Seventeen selected client module hashes are stable before/after; no complete transitive dependency lock is claimed.']
(target/'qualification.json').write_text(json.dumps(dict(status='VERIFIED',criterion='AC-03',source_cases=1,
    installed_cases=1,unique_new_cases=1,summary=summary,limits=limits,product_changes=0,
    clients=proof['clients'],packages=json.loads((installed/'package-proof.json').read_text())),indent=2)+'\n')
ledger_path=repo/'plans/agent_ops/ledger.json'
ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
item=ledger['completion_criteria']['AC-03']
item.update(status='VERIFIED',result=summary,remaining=[],qualification_limit=limits)
item['evidence']=sorted(set(item.get('evidence',[])+[prefix+'/qualification.json',prefix+'/installed/canonical/tests.xml',prefix+'/artifact-manifest.json']))
task=ledger['tasks']['DX-08']
task['subscopes']['two_existing_clients_directed_exchange']='VERIFIED'
task['files']=sorted(set(task['files']+[source_proof['test']]))
task['tests']=sorted(set(task['tests']+[prefix+'/installed/canonical/tests.xml']))
task['result']+=' AC03 now separately proves directed exchange and reconnect through two existing MCP clients; a separately consented handoff through the optional smoke facade remains unqualified.'
task['limitations']=['Complete the optional separately consented handoff smoke with the qualified external clients. The plan requires the canonical chain, not a model-generated marker; no paid-provider requirement is inferred for DX08 itself.']
criterion=ledger['completion_criteria']['AC-01']
criterion['remaining']=[text.replace('DX-08/AC-03 participação/cooperação','DX-08 smoke com handoff consentido') for text in criterion.get('remaining',[])]
ledger['campaigns']['r3_two_existing_mcp_clients']=dict(status='VERIFIED',source_cases=1,installed_cases=1,
    unique_new_cases=1,real_provider=False,evidence=[prefix+'/qualification.json',prefix+'/artifact-manifest.json'])
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='Two existing MCP clients',status='VERIFIED',
    summary='AC03 qualified with Inspector and FastMCP real TCP participation/reconnect;1source+1installed PASS. DX08 handoff and M1 remain separate.',evidence=[prefix+'/qualification.json']))
ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — dois clientes MCP existentes

AC-03 verificado: MCP Inspector0.21.2 programático e FastMCP2.14.7 abriram
sessões úteis, trocaram mensagem/resposta dirigida com correlação canônica e
reconectaram sem duplicar identidades ou sessões. Um caso passou na fonte e
no Server instalado; são duas execuções do mesmo caso. A tentativa inicial
com oráculo de DTO incorreto foi preservada. Não houve provedor, modelo,
credencial pessoal, adaptador nativo novo ou alteração de produto.
O handoff separadamente consentido de DX08 e a campanha M1 continuam abertos.
Evidência: `plans/agent_ops/evidence/r3-two-existing-mcp-clients/qualification.json`.
'''
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
(target/'milestone.md').write_text('# Two existing MCP clients\n\n'+summary+'\n\n'+'\n'.join('- '+v for v in limits)+'\n',encoding='utf-8')
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
findings=[dict(path=p.relative_to(target).as_posix(),sha256=hashlib.sha256(m.group()).hexdigest()) for p in target.rglob('*') if p.is_file() for pat in patterns for m in re.finditer(pat,p.read_bytes())]
assert not findings,findings
(target/'public-review.json').write_text(json.dumps(dict(findings=findings,scope='Finite allowlist; no private client/server stderr, homes, databases or credentials'),indent=2)+'\n')
files={p.relative_to(target).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files,scope='Exact public bytes'),indent=2)+'\n')
print(json.dumps(dict(criterion='AC-03',status='VERIFIED',unique_new_cases=1,artifacts=len(files))))
