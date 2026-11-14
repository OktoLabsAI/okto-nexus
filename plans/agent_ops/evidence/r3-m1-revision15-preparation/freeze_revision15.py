"""Freeze only the qualified offline revision; never dispatch a workflow step."""
from pathlib import Path
import ast,hashlib,json,xml.etree.ElementTree as ET
H=Path(__file__).resolve().parent;OLD=H.with_name('work-request12-package2')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
A=read(H/'amendment.json');digest=sha(H/'amendment.json')
assert read(H/'gate-qualification.json')['amendment_sha256']==digest
assert read(H/'probe-qualification.json')['status']=='CANONICAL_PROBE60_PASS'
for item in A['sources'].values():
    assert sha(item['path'])==item['sha256'];ast.parse(Path(item['path']).read_text(encoding='utf-8-sig'))
for name,count in [('checks/installed-preflight.xml',48),('checks/composition.xml',6)]:
    suites=list(ET.parse(H/name).getroot().iter('testsuite'))
    assert sum(int(s.get('tests',0)) for s in suites)==count
    assert not sum(int(s.get('errors',0))+int(s.get('failures',0)) for s in suites)
workflow=read(OLD/'workflow.json')
for step in workflow['steps']:
    step['argv']=[arg.replace(str(OLD),str(H)) for arg in step['argv']]
    step['argv'][step['argv'].index('--expected-amendment-sha256')+1]=digest
    step['label']={'useful12':'useful13','continuation13':'continuation14'}.get(step['label'],step['label'])
    if step['label']=='continuation14':step['conditional']='Only canonical useful13 SUCCEEDED, settled and same session; no continuation after failure.'
    if step['label']=='authorization-apply':step['conditional']='Only expired-grant canonical review plus exact root technical selection; never replace available grant.'
    if step['label']=='closure':assert str(H/'request_entry.py') in step['argv'] and str(H/'invoke_request.py') not in step['argv']
workflow.update(amendment_sha256=digest,remote_selectors_enabled=False,
    normal_fault_containment=A['normal_fault_containment'],native_decision_path=A['native_decision_path'],
    technical_selections={'upgrade_apply':'private/environment-upgrade-reviewed.json binds exact planSHA/revision after canonical plan.',
                          'grant_apply':'private/authorize-local-reviewed.json binds exact canonical expired reviewSHA/revision.'})
save(H/'workflow.json',workflow)
source_ancestry={}
for key,item in A['sources'].items():
    predecessor=read(OLD/'amendment.json')['sources'][key]
    source_ancestry[key]={'current':item,'ancestor':predecessor,'byte_equal':item['sha256']==predecessor['sha256']}
save(H/'source-ancestry.json',{'sources':source_ancestry,'original_frozen_unchanged':True})
plan=Path(A['execution_plan']['path']);(H/'selected-execution-plan.json').write_bytes(plan.read_bytes())
qualification={'status':'OFFLINE_REVISION15_QUALIFIED_NOT_EXECUTED','amendment_sha256':digest,
 'installation':pin(H/'package/installation.json'),'build':pin(H/'package/build-provenance.json'),
 'canonical_probe60':pin(H/'probe-qualification.json'),'composed_gate':pin(H/'gate-qualification.json'),
 'installed_preflight':{'passed':48,'tool':'40f99b','xml':pin(H/'checks/installed-preflight.xml'),
      'runner':pin(H/'checks/run_installed.py'),'origins':pin(H/'checks/installed-origins.json'),'repository_source_imports':False},
 'composition_delta':{'passed':6,'tool':'3d42be','xml':pin(H/'checks/composition.xml'),'runner':pin(H/'checks/run_composition.py'),
      'test_source':pin(H/'checks/test_composition.py'),'subsequent_test_edit':'Removed unused imports only; tests not rerun for that nonbehavioral edit.'},
 'controller_delta':pin(H/'controller-qualification/qualification.json'),
 'controller_runtime_freeze':pin(H/'controller-qualification/runtime-freeze.json'),
 'suite_counts_not_summed_as_distinct':True,'ruff_F':{'tool':'6ada7c','result':'PASS'},
 'real_work_import_prefix':{'tool':'adffbf','result':'PASS','handler_called':False,
     'editorial_rebind':'Canonical close intent name corrected to runtime.close; same gate revalidated against final amendment, no behavior or test change.'},
 'python':read(H/'package/installation.json')['python'],'python_flags':['-B','-I','-X','utf8'],
 'reused_unchanged_qualification':{'predecessor':pin(OLD/'qualification.json'),
      'scope':'Unchanged lifecycle/upgrade/authorization transport semantics; changes to context/history/policy/limits/facade/CLI preflight qualified separately. Prior totals not added.'},
 'policy':A['policy'],'observation_bounds':A['observation_bounds'],
 'new_model_reservations':0,'services_started':0,'provider_calls':0,'upgrade_actions':0,'grant_changes':0,
 'acceptance_promoted':False,'remote_execution_enabled':False,
 'historical_control_receipt':'SUBMITTED snapshot retained; no completion inferred from cancelled target or physical exit.'}
save(H/'qualification.json',qualification)
(H/'README.md').write_text('''Revision15 — preparação offline finita

Local útil13 em nova sessão e continuação14 somente após sucesso canônico na mesma
sessão. IDs remotos15/16 pertencem à alocação, mas seus seletores permanecem fechados
até qualificação separada. A autorização humana existente cobre700k tokens; esta
revisão técnica explicita12 reservas históricas +4 novas =16, sem novo consentimento
humano de hash. Carry295262, preventiva500k e tolerância700k permanecem explícitos.

Sete registros máximos observados (3 históricos+4 novos): snapshot1s, inicialização2s,
margem1s, poll17s/fresh18s/cadence22s e alvo200ms. São limites operacionais, não novo
critério de aceite. Deadline de trabalho600s. CLI readiness5s é opt-in explícito,
sem novo start/replay de POST; padrão do produto permanece uma inspeção.

Pacote próprio de archives Nexus46ba5c31/Connector645d7bd5 e Core7810/d881 existente.
1002 payloads verificados; probe60 passou.48 testes de preflight instalado,6 da
composição e14 deltas do controlador (12+2 rodadas) ficam separados, sem somar casos
distintos. Import real do prefixo work/facade passou sem chamar handler ou controller.

Roteiro: prepare → upgrade-plan → seleção técnica do plano exato → upgrade-apply →
install/start uma vez45s e observação passiva permitida180s → watcher de três processos
→ revisão de grant (apply só se expirado e selecionado) → útil13 → continuação14
condicional → stop normal → cleanup proof → uninstall → final presence → close direto.
Native decision usa private/native-decision.json, sempre revisão do pedido real.

Se uma falha deixar turno nativo admitido ativo e stop45 continuar draining, a
autorização existente permite contenção normal canônica exata: observar owner,
coorte, sessão/operação/turno; root revisa e seleciona um resolve+admit de interrupt,
sem novo turno ou replay de decisão. Session close apenas se necessário; stop e
provas físicas separados. A referência request12 não é comando reexecutável.

Request12 permanece CANCELLED e seu controle interrupt SUBMITTED; original checkpoint
e falhas não mudam. Cleanup não prova settlement. Falha antes de uso final exige
companion contábil pós-saída separado, preservando mínimo observado/unsettled.
Nenhuma execução de serviço, provedor, grant ou migração foi feita na preparação.
''',encoding='utf-8')
paths=[H/name for name in ('amendment.json','commands.json','workflow.json','qualification.json','README.md',
 'selected-execution-plan.json','technical-predecessor.json','source-ancestry.json','historical-grants.json',
 'build_packages.py','probe_new_package.py','probe-qualification.json','compose_revision15.py',
 'adapt_owned_sources.py','check_composed_gate.py','gate-qualification.json','gate-qualification-before-editorial.json','freeze_revision15.py',
 'package/build-provenance.json','package/installation.json','package/dependency-manifest.json',
 'package/prepare_dependencies.py','package/install_packages.py','checks/test_installed_preflight.py',
 'checks/run_installed.py','checks/installed-preflight.xml','checks/installed-origins.json',
 'checks/test_composition.py','checks/run_composition.py','checks/composition.xml')]
paths += [Path(p['path']) for p in A['sources'].values()]
paths += sorted(p for p in (H/'controller-qualification').rglob('*') if p.is_file() and p.suffix in ('.json','.py','.xml','.md'))
paths=list(dict.fromkeys(paths))
assert not (H/'public').exists() and not (H/'private').exists() and not (H/'runtime-private').exists()
manifest={'status':'FROZEN_OFFLINE_QUALIFIED_FINAL_ROOT_REVIEW_REQUIRED','amendment_sha256':digest,
 'files':{str(p.relative_to(H)).replace('\\','/'):pin(p) for p in paths},'no_runtime_effects':True,'remote_selectors_enabled':False}
save(H/'runtime-freeze.json',manifest)
save(H/'public-allowlist.json',{'files':[*manifest['files'].values(),pin(H/'runtime-freeze.json')],
 'excluded':['private','runtime-private','venv','wheels','sourcearchives','auth','transcripts','ownershiptoken/nonce']})
print(json.dumps({'amendment_sha256':digest,'freeze_sha256':sha(H/'runtime-freeze.json'),
 'qualification_sha256':sha(H/'qualification.json'),'allowlist_sha256':sha(H/'public-allowlist.json'),'files':len(paths)}))
