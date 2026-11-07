from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
temp=Path('C:/Users/jpamb/AppData/Local/Temp')
target=repo/'plans/agent_ops/evidence/r3-dx-final-contracts'
target.mkdir(exist_ok=True)
shutil.copytree(temp/'r3-dx-remaining-scenarios-go3nemvl',target/'audit',dirs_exist_ok=True)
inbox=temp/'r3-cooperative-drain-09ucmgsr/nexus-inbox-scope'
assert json.loads((inbox/'result.json').read_text())['exit']==0
assert json.loads((inbox/'canonical/campaign.json').read_text())['changed_inputs']==[]
locations={}
for p in inbox.rglob('*'):
    if not p.is_file() or p.suffix not in {'.json','.xml','.txt'}:continue
    dest=target/'inbox'/p.relative_to(inbox)
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(p,dest)
    locations[str(p)]={'published_path':dest.relative_to(repo).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
shutil.copy2(temp/'r3-cooperative-drain-09ucmgsr/qualify_inbox.py',target/'qualify_inbox.py')
shutil.copy2(temp/'prepare_inbox_check.py',target/'prepare_inbox_check.py')
shutil.copy2(__file__,target/'close_milestone.py')
(target/'evidence-location-map.json').write_text(json.dumps(locations,indent=2)+'\n')
(target/'preparation-note.json').write_text(json.dumps({'initial_shell_preparation':'A nested-quote Python -c preparation command failed with SyntaxError before file creation or test execution. Replaced with the retained prepare_inbox_check.py file.','test_failures':0,'product_changes':0},indent=2)+'\n')
data=json.loads((target/'audit/matrix.json').read_text(encoding='utf-8'))
ledger_path=repo/'plans/agent_ops/ledger.json'
d=json.loads(ledger_path.read_text(encoding='utf-8'))
prefix=target.relative_to(repo).as_posix()
for row in data['scenarios']:
    item=d['scenarios'][row['id']]
    assert item['requirement']==row['literal_requirement']
    item.update(status=row['proposed_status'],result=row['reason'],remaining=row['specific_pending'] or 'None within the literal contract and stated scope.',remaining_kind=row['pending_kind'],qualification_limit=row['limit'],common_qualification_limit=row['common_limit'])
    item['evidence']=sorted(set(item.get('evidence',[])+[prefix+'/audit/matrix.json',prefix+'/evidence-location-map.json',prefix+'/artifact-manifest.json']))
    if row['id']=='DX-T44':item['evidence'].append(prefix+'/inbox/canonical/tests.xml')
    item['verified_contract_subscopes']=row['verified_subscopes']
counts=data['status_counts']
d['campaigns']['r3_remaining_dx_contracts']={'status':'VERIFIED','scope':'Reconciliation of21 literal scenarios;16 contractual predicates verified and5 real campaign requirements still open','new_installed_existing_test_cases':3,'product_changes':0,'evidence':[prefix+'/milestone.md',prefix+'/artifact-manifest.json']}
d['updated_at']=datetime.now(timezone.utc).isoformat()
d['history'].append({'date':'2026-11-07','milestone':'Remaining DX literal contracts','status':'VERIFIED','summary':'16 additional DX contract predicates verified, T44 inbox isolation3/3 installed. Real provider/login/default-installation/effective-process scopes remain pending in T34/T38/T39/T40/T43. No provider or native task executed.','evidence':[prefix+'/milestone.md']})
ledger_path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — cenários DX restantes

Reconciliação literal dos21 cenários DX restantes:16 contratos verificados,
cinco campanhas reais mantidas pendentes (T34/T38/T39/T40/T43). O caso existente
de inbox alheia passou nos três parâmetros instalados (`count/peek/history`),
com as mesmas wheels, ambiente isolado e inputs inalterados. Os92 pares de
relatório/node da matriz são referências sobrepostas, não novos testes.
T50 verifica honestidade de aceite; não declara M1 concluído. Não houve produto,
credencial pessoal, provedor ou Task Scheduler alterado neste milestone.
Evidência: `plans/agent_ops/evidence/r3-dx-final-contracts/milestone.md`.
'''
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
(target/'milestone.md').write_text('''# Remaining DX contract predicates

Twenty-one fixed scenario texts were reconciled with current implementation and
exact retained assertions. Sixteen contract predicates are verified. DX-T34,
T38, T39, T40 and T43 retain their explicit real provider/login/installation/
effective-process campaign requirements. No M1/M2 or full R3 acceptance follows.

The one missing retained test for T44 ran against the current installed packages:
inbox_count, inbox_peek and inbox_history all refused another agent's inbox.
Three cases passed; pip check and immutable input/package checks passed.
The source test already existed; no product code or wheel changed. The initial
shell preparation quoting error occurred before any execution and is documented.

The audit's92 report/node references overlap earlier campaigns and are not92
new tests. Its original manifest and Temp paths remain immutable; the location
map binds the three new cases to their published exact-byte evidence. All real
client/vault/provider campaign boundaries remain explicit in the matrix.
''',encoding='utf-8')
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
findings=[]
for p in target.rglob('*'):
    if p.is_file():
        for pattern in patterns:
            for m in re.finditer(pattern,p.read_bytes()):findings.append({'path':str(p.relative_to(target)),'sha256':hashlib.sha256(m.group()).hexdigest()})
assert not findings,findings
(target/'public-review.json').write_text(json.dumps({'findings':findings,'scope':'Finite public allowlist pattern scan; no personal state enumerated'},indent=2)+'\n')
files={p.relative_to(target).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps({'files':files,'scope':'Exact public milestone bytes; nested audit manifest unchanged'},indent=2)+'\n')
print(json.dumps({'scenario_statuses':counts,'new_installed_tests':3,'files':len(files)}))
