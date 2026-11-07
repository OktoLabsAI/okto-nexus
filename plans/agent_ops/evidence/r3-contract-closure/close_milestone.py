from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil,subprocess

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
temp=Path('C:/Users/jpamb/AppData/Local/Temp')
target=repo/'plans/agent_ops/evidence/r3-contract-closure'
shutil.copytree(temp/'r3-ac08-docs-qc4jjmkz/public',target/'docs')
shutil.copytree(temp/'r3-svc-t26-t28-reconciliation-y9nmj5ad',target/'service-contracts')
shutil.copy2(__file__,target/'close_milestone.py')
matrix=json.loads((target/'matrix.json').read_text(encoding='utf-8'))
# The document correction is intentionally recorded after the matrix's first
# read; update only current source hashes, preserving retained XML hashes.
for row in matrix['rows']:
    for item in row['current_sources']:
        item['sha256']=hashlib.sha256((repo/item['path']).read_bytes()).hexdigest()
(target/'matrix.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
doc=json.loads((target/'docs/audit.json').read_text(encoding='utf-8'))
repos={'nexus':repo,'connector':repo.parent/'okto-nexus-connector','core':repo.parent/'okto-nexus-connector-core'}
doc_proof={}
for name,hashes in doc['changes'].items():
    owner,path=name.split('/',1)
    raw=(repos[owner]/path).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==hashes['after_sha256'],name
    normalized=raw.replace(b'\r\n',b'\n')
    doc_proof[name]={'working_sha256':hashes['after_sha256'],'normalized_sha256':hashlib.sha256(normalized).hexdigest(),'normalization':'CRLF-to-LF only if applicable'}
    if owner!='nexus':
        blob=subprocess.check_output(['git','-C',str(repos[owner]),'show','HEAD:'+path])
        assert blob in (raw,normalized)
        doc_proof[name]['published_commit']=subprocess.check_output(['git','-C',str(repos[owner]),'rev-parse','HEAD'],text=True).strip()
(target/'doc-publication-proof.json').write_text(json.dumps(doc_proof,indent=2)+'\n')
ledger_path=repo/'plans/agent_ops/ledger.json'
d=json.loads(ledger_path.read_text(encoding='utf-8'))
prefix=target.relative_to(repo).as_posix()
for folder in ('dx','service-contracts'):
    data=json.loads((target/folder/'matrix.json').read_text(encoding='utf-8'))
    for row in data['scenarios']:
        item=d['scenarios'][row['id']]
        assert item['requirement']==row['literal_requirement']
        assert row['proposed_status']=='VERIFIED' and row['specific_pending_for_literal'] is None
        item.update(status='VERIFIED',result=row['rationale'],remaining='None within the literal contract and explicitly stated qualification scope.',remaining_kind='none',qualification_limit=row['limit'])
        item['evidence']=sorted(set(item.get('evidence',[])+[prefix+'/'+folder+'/matrix.json',prefix+'/'+folder+'/verification.json',prefix+'/artifact-manifest.json']))
for key,reason in {
    'AC-05':'Explicit path inventory maps message/handoff creation, approvals, participant cooperation, work/native decisions, local/remote setup and grant issuance recovery to exact retained PASS nodes. Current39 recovery cases and historical actual process-death/atomic receipt proofs preserve IDs within documented retention windows; no universal exactly-once or real provider restart claim.',
    'AC-08':'Eight current documents corrected against installed help, current parsers and delivered APIs. Ten Nexus help calls,75 Connector parsers and29 published Core JSON resources were compared; schemas and product bytes unchanged. Historical evidence remains historical, and real qualifications remain explicitly open.',
    'AC-15':'Current installed Nexus and Connector real detached concurrent start/reuse/restart/drain cases pass under isolated profiles; exact foreground and passive status/log/doctor assertions are mapped. No registered native task or provider acceptance is inferred.'
}.items():
    item=d['completion_criteria'][key]
    item.update(status='VERIFIED',result=reason)
    extra=[prefix+'/docs/audit.json'] if key=='AC-08' else [prefix+'/matrix.json']
    if key=='AC-15':extra.append(prefix+'/controls/tests.xml')
    item['evidence']=sorted(set(item.get('evidence',[])+extra+[prefix+'/artifact-manifest.json']))
d['campaigns']['r3_contract_closure']={'status':'VERIFIED','scope':'18 literal scenarios and AC05/08/15, with exact stated contract limits; no global R3/M1/M2 acceptance','new_existing_test_runs':2,'new_product_tests':0,'new_help_commands':10,'connector_parsers_compared':75,'core_json_resources_compared':29,'docs_changed':8,'evidence':[prefix+'/milestone.md',prefix+'/artifact-manifest.json']}
d['updated_at']=datetime.now(timezone.utc).isoformat()
d['history'].append({'date':'2026-11-07','milestone':'Current documentation and finite contract closure','status':'VERIFIED','summary':'Corrected8docs, closed16DX andSVC-T26/T28 literal stale statuses plusAC05/08/15. Two current installed actual detached lifecycle tests passed. Core docs f9a5c3b andConnector docs55a14a6 pushed. T23/T24 dedicated restart tests remain separate ongoing work; real campaigns pending.','evidence':[prefix+'/milestone.md']})
ledger_path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — documentação vigente e contratos de recuperação

Corrigidos oito documentos dos três repos: fluxos já entregues deixaram de ser
descritos como futuros; referência Connector confere com75 parsers atuais;
API Core documenta drain cooperativo. Dez helps Nexus passaram e29 recursos
JSON Core conferem com a wheel. Core docs publicado em `f9a5c3b`, Connector em
`55a14a6`; produto e wheels inalterados.

Dois casos físicos existentes passaram nas wheels atuais, em perfis isolados:
Nexus e Connector com start concorrente, reuso, restart e drain, sem serviço
nativo/provedor. Matriz explícita fecha AC-05/08/15 dentro dos contratos;16DX e
SVC-T26/T28 passam a VERIFIED por provas específicas já retidas. Não se somam
nodes de relatórios sobrepostos nem se apresentam mocks como Task Scheduler.
T23/T24 ganham testes focais separados de restart real; sua aceitação ainda não
é antecipada. M1/M2 e campanhas reais permanecem abertos.

Evidência: `plans/agent_ops/evidence/r3-contract-closure/milestone.md`.
'''
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
(target/'milestone.md').write_text('''# Current interfaces and finite contract acceptance

Eight user-facing documents now match the delivered three-package behavior.
Ten Nexus help calls and the Connector parser import passed;75 Connector parsers
generate the corrected reference exactly, and29 Core JSON resources match the
installed wheel. Core/Connector document commits are recorded in the publication
proof. Product, schema and wheel bytes did not change.

Two existing tests ran against current installed packages in disposable Windows
profiles. Both actual detached CLIs exercised concurrent start, one owner, reuse,
restart and canonical drain. They passed with unchanged test inputs and exact
691/124/166-file package checks. No native task, provider or personal credentials
were used. Retained source tests and raw output delimit what was exercised.

The explicit AC05/15 path inventory checks81 report/node references; these are
not81 new tests. DX-T01…14/T26/T28 map78 retained references, and SVC-T26/T28 map50.
These mappings close their literal contracts with individual scope limits.
Old XMLs remain historical tests. Only the two detached tests ran in this step.
The real credential-to-client-to-cooperation chain, productive M1/M2 and native
service/login/logout/reboot campaigns remain separately unqualified.

The new T23/T24 real restart tests are ongoing separate work and are excluded
from this milestone. No completion of the fixed R3 plan is claimed.
''',encoding='utf-8')
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
findings=[]
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
for p in target.rglob('*'):
    if not p.is_file():continue
    for pattern in patterns:
        for m in re.finditer(pattern,p.read_bytes()):findings.append({'path':str(p.relative_to(target)),'sha256':hashlib.sha256(m.group()).hexdigest()})
assert not findings,findings
(target/'public-review.json').write_text(json.dumps({'findings':findings,'scope':'Finite pattern scan of this public allowlist only; no personal state enumerated','binary_files':0},indent=2)+'\n')
files={p.relative_to(target).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(target.rglob('*')) if p.is_file() and p.name!='artifact-manifest-root.json'}
(target/'artifact-manifest.json').write_text(json.dumps({'files':files,'scope':'Exact new milestone public artifacts; nested agent manifests retained unchanged'},indent=2)+'\n')
print(json.dumps({'scenarios_closed':18,'criteria_closed':['AC-05','AC-08','AC-15'],'files':len(files),'product_edits':0}))
