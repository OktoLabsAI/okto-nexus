from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil,xml.etree.ElementTree as ET

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=Path('C:/Users/jpamb/AppData/Local/Temp/m1-controller-xh414i40/public')
target=repo/'plans/agent_ops/evidence/r3-m1-controller'
manifest=json.loads((source/'manifest.json').read_text())
files_by_name={record['path']:record for record in manifest['files']}
assert len(files_by_name)==len(manifest['files'])
assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}==set(files_by_name)|{'manifest.json'}
for name,record in files_by_name.items():
    raw=(source/name).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==record['sha256'] and len(raw)==record['bytes']
final_xml=list(source.glob('**/run-gtxuhy58/*results.xml'))
if not final_xml:
    final_xml=[p for p in source.rglob('*.xml') if 'gtxuhy58' in p.as_posix()]
assert len(final_xml)==1,final_xml
cases=list(ET.parse(final_xml[0]).iter('testcase'))
assert len(cases)==14 and not any(c.find(k) is not None for c in cases for k in ('failure','error','skipped'))
assert not target.exists()
shutil.copytree(source,target/'preparation')
shutil.copy2(__file__,target/'close_milestone.py')
prefix=target.relative_to(repo).as_posix()
old=repo/'plans/agent_ops/evidence/r3-m1-token-accounting/m1-codex-campaign-proposal-v6.json'
proposal=json.loads(old.read_text(encoding='utf-8'))
proposal['revision']=7
proposal['status']='PREPARED_AWAITING_EXPLICIT_EXECUTION_AUTHORIZATION'
proposal['token_accounting']['collector_preparation']['controller_integration_complete']=True
proposal['token_accounting']['collector_preparation']['integration_qualification']='Installed synthetic composition only; no real provider/service campaign.'
proposal['token_accounting']['controller_preparation']=dict(
    evidence=prefix+'/preparation/README.md',final_unique_tests=14,
    scope='Finite single-owner controller: canonical work events plus distinct owned standalone setup journal, shared six-admission allocation and100k preventive interruption/deadline120.',
    qualification='Installed Nexus/Core with synthetic executor; real native/provider/OS service behavior remains pending.')
proposal['blocking_preconditions_before_execution_request']=[
    'Explicitly authorize native use of the pinned existing provider home and the finite M1 work. Budget tolerance has been clarified; credential/inference approval is still separate.',
    'Explicitly authorize the two exact M1 user tasks and eight lifecycle actions, separately from the24-action empty-service proposal using two other temporary tasks.'
]
proposal['preflight_before_effects']=[
    'Recheck pinned artifacts, exact task absence/ownership, scratch-path absence and port immediately before effects; stop on mismatch rather than silently replace targets.',
    'Create only the reviewed disposable directories and fixtures; arm/persist the finite controller before the first setup test.',
    'Attach the exact owned-home stop callbacks and existing canonical operator/work transports. Keep the controller single-owner; persist reservations before dispatch and poll within its documented operational interval.',
    'The standalone setup source is the actual Nexus connection-test journal. Do not invent a second remote setup journal: if the Connector path adds consumption from an unknown source, stop before continuing.',
    'Record observed counters as minimums, not final billing totals. Stop new admissions on incomplete/unknown accounting; never replay productive work to repair monitoring.'
]
proposal['authorization_request_summary']=dict(
    provider='Codex0.157.0 isolated official package; native use of existing authenticated C:/Users/jpamb/.codex context, without reading/copying its credential files by the agent.',
    productive_admissions_maximum=6,serial=True,total_token_tolerance=700000,preventive_threshold=100000,
    m1_service_tasks=2,m1_lifecycle_actions=8,separate_empty_service_tasks=2,separate_empty_lifecycle_actions=24,
    excludes=['Personal executable/config replacement','Unowned tasks/processes','Logout/reboot','Merge/package publication','Extra autonomous turns'])
proposal['supersedes_proposal_sha256']=hashlib.sha256(old.read_bytes()).hexdigest()
proposal['supersedes_proposal_path']=old.relative_to(repo).as_posix()
proposal['revision_note']='Finite controller composition qualified with14final installed synthetic cases. Prior intervened diagnostic and13case run retained separately. Preparation is now reviewable; no native account, inference or service action authorized/executed and no plan acceptance promoted.'
(target/'m1-codex-campaign-proposal-v7.json').write_text(json.dumps(proposal,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — controlador finito M1 preparado

Composição final verificada em 14 casos com Nexus/Core instalados e executor
sintético: journal próprio de setup e eventos canônicos de trabalho compartilham
orçamento e seis reservas; perda de resposta recupera os mesmos IDs; preventiva
de 100 mil e prazo de 120 s selecionam controles canônicos do trabalho ou stop
do dono temporário. Lock exclusivo impede dois controladores; reconstrução
exige reanexar as capacidades de parada correspondentes ao home selecionado.

Os journals anteriores, atribuídos e fechados, são preservados; apenas um novo
journal é aceito por reserva serial. O monitor projeta metadados/uso no SQLite,
sem exportar prompts, respostas ou credenciais. Setup encerrado exige namespace
exato e reserva própria liberada, além de close SUBMITTED/SUCCEEDED conforme o
contrato standalone do Core; SUBMITTED isolado não comprova encerramento.

A primeira rodada teve 1 falha/12 passes e intervenção de cleanup para remover
um gap artificial; permanece diagnóstica, sem aceite. Após correções do oráculo
e finalizer, passaram 13 casos e depois os 14 finais, incluindo negativo de slot
ainda ocupado. A qualificação final é 14 casos únicos, não soma de execuções;
994 inputs ficaram iguais, sem sombras de módulos de produto pelo checkout.

A proposta v7 consolida 700 mil tokens de tolerância, preventiva de 100 mil,
até seis admissões seriais e os recursos exatos. O coletor permanece operacional,
sem garantia de contador final ou corte atômico. Esta preparação não comprova
M1, provider, Connector real ou serviço do SO. A execução real ainda aguarda
autorização para conta e ações de serviço; nenhum status de aceite foi promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-controller/m1-codex-campaign-proposal-v7.json`.
'''
(target/'milestone.md').write_text(note.lstrip(),encoding='utf-8')
lp=repo/'plans/agent_ops/ledger.json'
ledger=json.loads(lp.read_text(encoding='utf-8'))
campaign=ledger['campaigns']['m1_codex_real']
campaign.update(status='PROPOSAL_READY_AWAITING_EXECUTION_AUTHORIZATION',
    proposal=prefix+'/m1-codex-campaign-proposal-v7.json',
    controller_preparation=dict(status='SYNTHETIC_INSTALLED_VERIFIED',final_unique_passes=14,
        evidence=prefix+'/artifact-manifest.json',real_campaign_executed=False))
campaign['token_collector_preparation'].update(controller_integration_complete=True,
    integration_qualification='Installed synthetic only; native/provider/service campaign pending.')
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='Finite M1 campaign controller prepared',status='PREPARED',
    summary='14final installed synthetic cases qualify setup/work shared accounting, recovery and owned abort;994inputs unchanged. Initial intervened run retained. Proposal v7 ready for explicit execution approval; no provider or OS effects.',
    evidence=[prefix+'/milestone.md']))
lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}']
assert not [(p.name,hashlib.sha256(match.group()).hexdigest()) for p in target.rglob('*') if p.is_file()
    for pattern in patterns for match in re.finditer(pattern,p.read_bytes())]
files={p.relative_to(target).as_posix():dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files,scope='Installed synthetic preparation only; no provider/OS campaign acceptance'),indent=2)+'\n')
print(json.dumps(dict(final_unique_passes=14,proposal_revision=7,public_payloads=len(files))))
