from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,sys

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
temp=Path('C:/Users/jpamb/AppData/Local/Temp')
root=temp/'r3-cooperative-drain-09ucmgsr'
installed=root/'nexus-two-mcp-cooperation'
source=temp/'dx08-client-cooperation-fyxtns1b/public-final'
target=repo/'plans/agent_ops/evidence/r3-two-mcp-cooperation'
assert len(sys.argv)==2, 'exact installed pytest root required'
pytest_root=Path(sys.argv[1])
result=json.loads((installed/'result.json').read_text())
campaign=json.loads((installed/'canonical/campaign.json').read_text())
assert result['exit']==0 and result['cases']==2 and not result['failures'] and not result['skips']
assert campaign['status']=='PASS' and campaign['changed_inputs']==[]
assert (installed/'pip-check.txt').read_text().strip()=='No broken requirements found.'
external=json.loads((installed/'external-client-proof.json').read_text())
assert external['unchanged_before_and_after']
source_proof=json.loads((root/'mcp-cooperation-source-proof.json').read_text())
for name,sha in source_proof['files'].items():
    assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==sha
    assert (repo/name).read_bytes()==(root/'nexus-source-v1'/name).read_bytes()
source_manifest=json.loads((source/'artifact-manifest.json').read_text())
for entry in source_manifest['public_allowlist']:
    assert hashlib.sha256((source/entry['path']).read_bytes()).hexdigest()==entry['sha256']
proofs=[]
for directory in pytest_root.iterdir():
    if not directory.is_dir() or not re.search(r'\d+$',directory.name):continue
    for name in ('owner-proofs.json','public-client-proof.json','public-cooperation-proof.json'):
        p=directory/name
        if not p.exists():continue
        assert p.stat().st_mtime >= datetime.fromisoformat(campaign['started_at']).timestamp()
        document=json.loads(p.read_text())
        if name=='owner-proofs.json':assert len(document)==1 and document[0]['state']=='canonically_drained_owner_exited'
        elif name=='public-cooperation-proof.json':
            assert all(document[k] for k in ('separate_consents','wrong_consent_refused','result_verified_in_canonical_table','resumed_same_ids','identities_and_bindings_unchanged'))
            assert document['productive_calls']==['message_create','handoff_create']
            assert document['claim_epoch']>0 and document['runtime_operations']==0
        else:assert document['reconnect_same_sessions'] and document['identity_and_bindings_unchanged']
        proofs.append(p)
assert len(proofs)==4
assert not target.exists()
target.mkdir()
locations={}
def copy(p,relative):
    destination=target/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(p.read_bytes())
    locations[str(p)]=dict(published_path=destination.relative_to(repo).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
for p in source.rglob('*'):
    if p.is_file():copy(p,Path('source')/p.relative_to(source))
for p in installed.rglob('*'):
    if p.is_file() and p.suffix in {'.json','.xml','.txt'}:copy(p,Path('installed')/p.relative_to(installed))
for p in proofs:copy(p,Path('installed-observations')/p.relative_to(pytest_root))
for name in ('qualify_mcp_cooperation.py','mcp-cooperation-source-proof.json'):copy(root/name,name)
copy(temp/'prepare_mcp_cooperation_qualification.py','prepare_mcp_cooperation_qualification.py')
copy(temp/'r3-dx08-client-review-0hro7rrb/readonly-review.json','readonly-review.json')
copy(Path(__file__),'close_milestone.py')
(target/'evidence-location-map.json').write_text(json.dumps(locations,indent=2)+'\n')
prefix=target.relative_to(repo).as_posix()
summary='Existing Inspector and FastMCP clients complete TerminalCooperation directed exchange and separately consented handoff over real TCP. Wrong or premature consent has no effects. Peer claim_epoch and non-null result are canonical. CooperationFiles checkpoints reconstruct the facade and recover original IDs without another productive call or changed database effects.'
limits=['Scripted real distributed MCP clients and synthetic non-null result; no model or paid provider.',
        'Facade/checkpoint reconstruction, not a new process-crash qualification.',
        'Bindings are empty and stay empty; no preexisting productive binding preservation is claimed.',
        'The shared client driver changed, so the prior AC03 participation case was rerun together with the new DX08 case.',
        'No credential launcher/vault chain, native scheduled task, M1 or full M2 acceptance is inferred.']
(target/'qualification.json').write_text(json.dumps(dict(status='VERIFIED',task='DX-08',source_cases=2,
    installed_cases=2,new_unique_cases=1,requalified_existing_cases=1,summary=summary,limits=limits,
    product_changes=0,packages=json.loads((installed/'package-proof.json').read_text())),indent=2)+'\n')
ledger_path=repo/'plans/agent_ops/ledger.json'
ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
task=ledger['tasks']['DX-08']
task.update(status='VERIFIED',result=summary,limitations=limits)
task['subscopes']['qualified_external_client_cooperation']='VERIFIED'
task['subscopes']['two_existing_clients_directed_exchange']='VERIFIED'
task['files']=sorted(set(task['files']+list(source_proof['files'])))
task['tests']=sorted(set(task['tests']+[prefix+'/installed/canonical/tests.xml',prefix+'/qualification.json']))
task['reconciliation'].update(current_scope=summary,evidence=prefix+'/qualification.json')
criterion=ledger['completion_criteria']['AC-03']
criterion['evidence']=sorted(set(criterion['evidence']+[prefix+'/qualification.json',prefix+'/installed/canonical/tests.xml']))
criterion=ledger['completion_criteria']['AC-01']
criterion['remaining']=[text.replace('DX-08 smoke com handoff consentido e ','').replace('DX-08 smoke com handoff consentido; ','') for text in criterion.get('remaining',[])]
criterion['remaining']=[text for text in criterion['remaining'] if 'DX-08' not in text]+['Other mandatory real campaign evidence remains pending in the individually named task records; DX08 consented handoff smoke is now qualified.']
ledger['campaigns']['r3_two_mcp_cooperation']=dict(status='VERIFIED',source_cases=2,installed_cases=2,
    new_unique_cases=1,requalified_existing_cases=1,evidence=[prefix+'/qualification.json',prefix+'/artifact-manifest.json'])
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='Two-client consented cooperation',status='VERIFIED',
    summary='DX08 verified with separately consented canonical handoff; AC03 helper extension requalified.2source+2installed PASS, one new case, no provider/product change.',evidence=[prefix+'/qualification.json']))
ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — smoke de cooperação com dois clientes

DX-08 verificado com Inspector/FastMCP e TerminalCooperation/CooperationFiles
reais: troca dirigida, consentimento separado do handoff, claim/epoch e resultado
canônicos. Consentimento errado/antecipado não cria efeitos. Reconstituir a
fachada recupera os mesmos IDs sem novas chamadas produtivas. Dois casos passaram
na fonte e nos pacotes instalados: um novo e o caso AC03 requalificado porque o
helper compartilhado mudou. Não houve produto, modelo, credencial pessoal ou
serviço nativo alterado. M1 e launcher/cofre de DX04 continuam separados.
Evidência: `plans/agent_ops/evidence/r3-two-mcp-cooperation/qualification.json`.
'''
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
(target/'milestone.md').write_text('# Two-client cooperation\n\n'+summary+'\n\n'+'\n'.join('- '+v for v in limits)+'\n',encoding='utf-8')
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
findings=[dict(path=p.relative_to(target).as_posix(),sha256=hashlib.sha256(m.group()).hexdigest()) for p in target.rglob('*') if p.is_file() for pat in patterns for m in re.finditer(pat,p.read_bytes())]
assert not findings,findings
(target/'public-review.json').write_text(json.dumps(dict(findings=findings,scope='Finite public allowlist; no private runtime homes/databases/stderr or credentials'),indent=2)+'\n')
files={p.relative_to(target).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files),indent=2)+'\n')
print(json.dumps(dict(task='DX-08',status='VERIFIED',installed_cases=2,new_unique_cases=1,artifacts=len(files))))
