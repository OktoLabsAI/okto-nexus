"""Freeze selected finite revision17 after composition checks; no runtime effects."""
from pathlib import Path
import ast,hashlib,json,xml.etree.ElementTree as ET
H=Path(__file__).resolve().parent;OLD=H.with_name('work-revision16')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8',newline='\n')
A=read(H/'amendment.json');digest=sha(H/'amendment.json')
assert read(H/'gate-qualification.json')['amendment_sha256']==digest
assert read(H/'checks/quote-qualification.json')['status']=='DISPOSABLE_POWERSHELL_ABSOLUTE_RTK_PYTHON_QUOTE_PASS'
for item in A['sources'].values():
    assert sha(item['path'])==item['sha256'];ast.parse(Path(item['path']).read_text(encoding='utf-8-sig'))
suites=list(ET.parse(H/'checks/composition.xml').getroot().iter('testsuite'))
assert sum(int(s.get('tests',0)) for s in suites)==10
assert not sum(int(s.get('errors',0))+int(s.get('failures',0)) for s in suites)
workflow=read(OLD/'workflow.json')
workflow['steps']=[step for step in workflow['steps'] if not step['label'].startswith('upgrade-')]
for step in workflow['steps']:
    # Preserve argv[0] exactly: package remains in W16; only entry/amendment references move.
    step['argv']=[step['argv'][0],*[arg.replace(str(OLD),str(H)) for arg in step['argv'][1:]]]
    step['argv'][step['argv'].index('--expected-amendment-sha256')+1]=digest
    step['label']={'useful14':'useful15','continuation15':'continuation16'}.get(step['label'],step['label'])
    if step['label']=='continuation16':step['conditional']='Only useful15 is canonical SUCCEEDED, settled, useful/report confirmed and same session; old continuation15 is ineligible.'
    if step['label']=='useful15':step['conditional']='Only exact fresh canonical expired-grant review and selected issuance confirmed; no available old grant, no model replay.'
    if step['label'] in ('start','authorization-review'):step['not_before_utc']=A['grant_plan']['old_expiry_utc']
    if step['label']=='closure':assert str(H/'request_entry.py') in step['argv'] and str(H/'invoke_request.py') not in step['argv']
workflow.update(amendment_sha256=digest,normal_fault_containment=A['normal_fault_containment'],
 native_decision_path=A['native_decision_path'],remote_selectors_enabled=False,
 package_reused_unchanged=True,migration_actions=0,
 grant_review_semantics='Clock gate permits observation only; canonical available remains blocked, never inferred expired. Exact selected CAS recover/issue once only after expired review.',
 technical_selections={'grant_apply':'private/authorize-local-reviewed.json binds exact canonical expired review SHA/revision; technical root selection under standing authority.'})
save(H/'workflow.json',workflow)
ancestor=read(OLD/'amendment.json')
save(H/'source-ancestry.json',{'sources':{k:{'current':v,'ancestor':ancestor['sources'][k],
 'byte_equal':v['sha256']==ancestor['sources'][k]['sha256']} for k,v in A['sources'].items()},
 'original_frozen_unchanged':True,'removed_executable_selector':'upgrade; no migration for reused package'})
(H/'selected-execution-plan.json').write_bytes(Path(A['execution_plan']['path']).read_bytes())
qualification={'status':'OFFLINE_REVISION17_QUALIFIED_NOT_EXECUTED','amendment_sha256':digest,
 'selected_plan':A['execution_plan'],'installation_reused':A['installation'],
 'package_qualification_reused':pin(OLD/'qualification.json'),'package_freeze_reused':pin(OLD/'runtime-freeze.json'),
 'canonical_probe60_reused':pin(OLD/'probe-qualification.json'),
 'installed_native50_reused':{'xml':pin(OLD/'checks/installed-native.xml'),'passed':50,'elapsed_seconds':186.63,'executed_in_revision17':False},
 'connector_provenance':'Actual pip ZIP e1d1046d7bddfbaa116669e937430770ac1876278f192923614dc855d68e36aa remains recorded. Retained ZIP f9864f13db4c5e6e5afdfd8f28ca5384512a17a1f8efb1897cb3a4d810d43cf4 has 132 equal ZIP entries; 131 installed payloads exclude RECORD. No reinstall or origin rewrite.',
 'composition_delta':{'passed':10,'tool':'9c7076','elapsed_seconds':13.35,
  'xml':pin(H/'checks/composition.xml'),'runner':pin(H/'checks/run_composition.py'),'tests':pin(H/'checks/test_composition.py'),
  'scope':'Current facade/prompt/prefix, five historical records and honest closure, no upgrade/remote selection, expiry boundary, available-one-action vs expired review, receipt uncertainty, disposable real PowerShell RTK/Python quoting.'},
 'quote_fixture':pin(H/'checks/quote-qualification.json'),'composed_gate':pin(H/'gate-qualification.json'),
 'controller_delta':pin(H/'controller-qualification/qualification.json'),
 'controller_runtime_freeze':pin(H/'controller-qualification/runtime-freeze.json'),
 'counts_separate':{'controller_delta':12,'composition_delta':10,'prior_installed_reused':50,'new_installed_suite_runs':0},
 'runtime_sources_parsed':len(A['sources']),
 'root_review':{'context_lifecycle_grant_close':'65139f+c5a33b PASS','controller':'421420 PASS; finish_reader_cache peer PASS'},
 'policy':A['policy'],'observation_bounds':A['observation_bounds'],'prompt_exact_selected_plan':True,
 'service_context_reused':A['reused_service_context'],'new_builds':0,'new_venvs':0,'pip_runs':0,'probe_runs':0,
 'services_started':0,'provider_calls':0,'migration_actions':0,'grant_changes':0,'new_model_reservations':0,
 'acceptance_promoted':False,'remote_execution_enabled':False,
 'scope':'Technical finite local15/16 only; old useful14 SUCCEEDED but useful/report false. All uncertainty and original artifacts retained; no receipt completion synthesized.'}
save(H/'qualification.json',qualification)
(H/'README.md').write_text('''Revisão17 — composição offline finita

Reutiliza sem mutação o pacote e Python da revisão16:1002 payloads, probe60
e50 testes instalados anteriores permanecem vinculados por hash. Nenhum build,
pip, venv novo, probe repetido ou migração. A proveniência dos dois ZIPs Connector
continua explícita na qualificação anterior; não houve reinstalação.

Carry460793 tokens/14 reservas. Quatro IDs técnicos novos, máximo18; somente
útil15 e continuação16 local selecionáveis. Remoto17/18 bloqueado. Preventiva600k,
tolerância700k:139207/239207 restantes, sem garantia de conclusão ou billing final.
Cinco históricos mais dois locais cabem em oito registros: snapshot1/init2,
poll19/fresh20/cadence24/alvo200ms. Deadline600/readiness5/start45/passiva180 intactos.

Prompt exatamente selecionado no plano110c339: RTK e Python absolutos pinados,
sem alterar PATH/política. Quote foi testado somente em CSV/relatório sintéticos;
nenhuma resposta calculada do CSV real foi fornecida ao modelo ou pré-executada.

O grant492ad tem mínimo observado used2/max3. Start/review não selecionáveis antes
23:27:07.998684Z14/11/2026. Isso só permite observação: revisão canônica deve
confirmar todos expirados/can_issue antes seleção CAS e emissão única. Available
inesperado é bloqueio reportado, sem issue/trabalho e sem fingir expiração.

workflow.json: prepare, install/start único, watcher3handles, revisão/emissão
canônica selecionada, útil15, continuação16 somente após resultado útil na mesma
sessão, normalstop, provas, uninstall, presença final e closure direto. Native
decision fica em private/native-decision.json; apenas decisão real revisada.
Contenção normal turn.interrupt exata se stop45 persistir draining conserva o
padrão já revisado. Sem força, novo turno ou replay de decisão antiga.

Histórico14 canonicamente SUCCEEDED não produziu relatório útil; nenhuma promoção
de aceite. Recibos históricos permanecem snapshots sem conclusão inferida.
12 deltas controlador e10 composição são qualificados separadamente;50 installed
anteriores não foram repetidos. Nenhum serviço/modelo/grant foi executado.
''',encoding='utf-8',newline='\n')
names=['amendment.json','commands.json','workflow.json','qualification.json','README.md','selected-execution-plan.json',
 'technical-predecessor.json','historical-grants.json','source-ancestry.json','compose_revision17.py','freeze_revision17.py',
 'check_composed_gate.py','gate-qualification.json','checks/test_composition.py','checks/run_composition.py',
 'checks/composition.xml','checks/quote-qualification.json']
paths=[H/n for n in names]+[Path(v['path']) for v in A['sources'].values()]
paths+=sorted(p for p in (H/'controller-qualification').rglob('*') if p.is_file() and p.suffix in ('.json','.py','.xml','.md'))
paths=list(dict.fromkeys(paths))
assert not any((H/n).exists() for n in ('public','private','runtime-private','package'))
manifest={'status':'FROZEN_OFFLINE_QUALIFIED_FINAL_ROOT_REVIEW_REQUIRED','amendment_sha256':digest,
 'files':{str(p.relative_to(H)).replace('\\','/'):pin(p) for p in paths},'no_runtime_effects':True,'remote_selectors_enabled':False}
save(H/'runtime-freeze.json',manifest)
save(H/'public-allowlist.json',{'files':[*manifest['files'].values(),pin(H/'runtime-freeze.json')],
 'excluded':['private','runtime-private','venv','wheels','sourcearchives','auth','transcripts','ownershiptoken/nonce'],
 'reused_external_proofs':'Exact references in qualification; no package files duplicated.'})
print(json.dumps({k:sha(H/v) for k,v in {'amendment':'amendment.json','freeze':'runtime-freeze.json',
 'qualification':'qualification.json','allowlist':'public-allowlist.json','workflow':'workflow.json'}.items()}))
