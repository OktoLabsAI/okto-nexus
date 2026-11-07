from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=Path('C:/Users/jpamb/AppData/Local/Temp/r3-ac-finite-audit-erg387do')
target=repo/'plans/agent_ops/evidence/r3-acceptance-contracts'
assert not target.exists()
manifest=json.loads((source/'artifact-manifest.json').read_text())
for entry in manifest['public_allowlist']:
    assert hashlib.sha256((source/entry['path']).read_bytes()).hexdigest()==entry['sha256']
shutil.copytree(source,target/'audit')
shutil.copy2(__file__,target/'close_milestone.py')
matrix=json.loads((source/'matrix.json').read_text(encoding='utf-8'))
ledger_path=repo/'plans/agent_ops/ledger.json'
ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
prefix=target.relative_to(repo).as_posix()
for row in matrix['rows']:
    item=ledger['completion_criteria'][row['id']]
    assert item['requirement']==row['literal_requirement']
    item.update(status=row['proposed_status'],result=row['reason'],qualification_limit=row['limit'],remaining=row['remaining_work'])
    item['evidence']=sorted(set(item.get('evidence',[])+[prefix+'/audit/matrix.json',prefix+'/audit/proofs.json',prefix+'/artifact-manifest.json']))
    if row['id']=='AC-14':
        item['remaining']=['Real suspension/resume with known operation/owner and no inferred replay, authority renewal or claim release remains unqualified.']
        item['result']+=' Subsequent milestone03b3e801 qualifies real Server crash/return and live owned child restart with four current installed PASS; the audit is retained unchanged at its original point in time.'
        item['evidence'].append('plans/agent_ops/evidence/r3-service-restart-contracts/qualification.json')
ledger['campaigns']['r3_acceptance_contracts']=dict(status='VERIFIED',accepted=['AC-02','AC-12','AC-16','AC-17'],
    new_tests=0,retained_report_node_references=74,evidence=[prefix+'/milestone.md',prefix+'/artifact-manifest.json'])
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='Finite acceptance contract reconciliation',status='VERIFIED',
    summary='AC02/12/16/17 verified by explicit retained predicates; AC01/03/11/13/14 remain open with concrete evidence gaps. No new provider or service campaign inferred.',evidence=[prefix+'/milestone.md']))
ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — critérios de aceite contratuais

AC-02/12/16/17 verificados pela composição entre frentes, exclusividade de
instâncias, identidade/preset/limites e preservação da configuração. Auditoria
conferiu74 pares relatório/node existentes e82 entradas públicas estáveis;
não são74 testes novos. AC-01/03/11/13/14 continuam abertos com lacunas literais
específicas. A qualificação de reinício03b3e801 complementa AC14; suspensão real
permanece pendente. Dois clientes MCP podem ter qualificação direta sem provedor
se essa capacidade for comprovada; initialize sozinho não basta. Nenhum código
de produto, inferência ou registro nativo mudou neste milestone.
Evidência: `plans/agent_ops/evidence/r3-acceptance-contracts/milestone.md`.
'''
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
(target/'milestone.md').write_text('# Finite acceptance contracts\n\n'+note.split('\n\n',1)[1],encoding='utf-8')
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}']
assert not [(p.name,hashlib.sha256(m.group()).hexdigest()) for p in target.rglob('*') if p.is_file() for pat in patterns for m in re.finditer(pat,p.read_bytes())]
files={p.relative_to(target).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files,note='Original audit immutable; AC14 later qualification recorded in ledger'),indent=2)+'\n')
print(json.dumps(dict(accepted=['AC-02','AC-12','AC-16','AC-17'],new_tests=0,artifacts=len(files))))
