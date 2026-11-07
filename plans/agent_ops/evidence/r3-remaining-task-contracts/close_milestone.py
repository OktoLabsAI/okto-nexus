from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=Path('C:/Users/jpamb/AppData/Local/Temp/r3-nine-implemented-audit-g2d3zaeq')
target=repo/'plans/agent_ops/evidence/r3-remaining-task-contracts'
manifest=json.loads((source/'artifact-manifest.json').read_text())
for entry in manifest['artifacts']:
    assert hashlib.sha256((source/entry['path']).read_bytes()).hexdigest()==entry['sha256']
assert not target.exists()
shutil.copytree(source,target/'audit')
shutil.copy2(__file__,target/'close_milestone.py')
matrix=json.loads((source/'matrix.json').read_text(encoding='utf-8'))
ledger_path=repo/'plans/agent_ops/ledger.json'
ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
prefix=target.relative_to(repo).as_posix()
for row in matrix['tasks']:
    item=ledger['tasks'][row['id']]
    assert item['title']==row['title']
    if row['id']=='DX-08':
        assert item['status']=='VERIFIED'
        continue  # Later installed4455b841 supersedes this audit's pending note.
    item.update(status=row['recommendation'],result=row['conclusion'],
        remaining_evidence=row['minimal_remaining_evidence'],
        limitations=[row['gate_analysis']])
    item['tests']=sorted(set(item.get('tests',[])+[prefix+'/audit/matrix.json',prefix+'/artifact-manifest.json']))
    item['contract_reconciliation']=dict(evidence=prefix+'/audit/matrix.json',
        product_gap=row['product_gap'],previous_overbroad_limit=row['stale_or_overbroad_limit'])
ledger['campaigns']['r3_remaining_task_contracts']=dict(status='VERIFIED',accepted=['DX-15','DX-16'],
    new_tests=0,retained_pass_records_checked=63,retained_xml_reports=12,
    evidence=[prefix+'/milestone.md',prefix+'/artifact-manifest.json'])
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='Remaining task contract reconciliation',status='VERIFIED',
    summary='DX15/DX16 verified; six remaining implemented tasks retain their own concrete campaign gaps. Original nine-task audit preserves pendingDX08;4455b841 already qualifies it. No product/tests changed.',evidence=[prefix+'/milestone.md']))
ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — contratos de tarefas restantes

DX-15 e DX-16 verificados por suas provas literais de fachada/reuso e descoberta/
revisão. A auditoria conferiu63 registros PASS em12 XMLs e62 hashes; não executou
testes novos. BASE06/SVC07/DX04/DX17/DX18/DX20 mantêm as lacunas mínimas próprias:
primeiro uso e configuração reais, encerramento externo e launcher/credencial.
DX08, ainda pendente na matriz original, foi concluído depois em4455b841 e não
foi rebaixado. Não se exige inferência paga por definição para provar DX04.
M1 e as campanhas de serviço/plataforma continuam pendentes.
Evidência: `plans/agent_ops/evidence/r3-remaining-task-contracts/milestone.md`.
'''
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
(target/'milestone.md').write_text('# Remaining task contracts\n\n'+note.split('\n\n',1)[1],encoding='utf-8')
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}']
assert not [(p.name,hashlib.sha256(m.group()).hexdigest()) for p in target.rglob('*') if p.is_file() for pat in patterns for m in re.finditer(pat,p.read_bytes())]
files={p.relative_to(target).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files,scope='Original audit and later finite adjudication'),indent=2)+'\n')
print(json.dumps(dict(accepted=['DX-15','DX-16'],new_tests=0,artifacts=len(files))))
