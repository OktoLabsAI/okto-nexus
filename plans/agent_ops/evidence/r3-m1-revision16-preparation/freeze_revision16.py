"""Freeze qualified finite offline revision16; no lifecycle or provider invocation."""
from pathlib import Path
import ast,hashlib,json,xml.etree.ElementTree as ET
H=Path(__file__).resolve().parent;OLD=H.with_name('work-revision15')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8',newline='\n')
A=read(H/'amendment.json');digest=sha(H/'amendment.json')
assert read(H/'gate-qualification.json')['amendment_sha256']==digest
assert read(H/'probe-qualification.json')['status']=='CANONICAL_PROBE60_PASS'
for item in A['sources'].values():
    assert sha(item['path'])==item['sha256'];ast.parse(Path(item['path']).read_text(encoding='utf-8-sig'))
for name,count in [('checks/installed-native.xml',50),('checks/composition.xml',6)]:
    suites=list(ET.parse(H/name).getroot().iter('testsuite'))
    assert sum(int(s.get('tests',0)) for s in suites)==count
    assert not sum(int(s.get('errors',0))+int(s.get('failures',0)) for s in suites)
workflow=read(OLD/'workflow.json')
for step in workflow['steps']:
    step['argv']=[arg.replace(str(OLD),str(H)) for arg in step['argv']]
    step['argv'][step['argv'].index('--expected-amendment-sha256')+1]=digest
    step['label']={'useful13':'useful14','continuation14':'continuation15'}.get(step['label'],step['label'])
    if step['label']=='continuation15':step['conditional']='Only canonical useful14 SUCCEEDED, settled and same session; no continuation after failure.'
    if step['label']=='closure':assert str(H/'request_entry.py') in step['argv'] and str(H/'invoke_request.py') not in step['argv']
workflow.update(amendment_sha256=digest,normal_fault_containment=A['normal_fault_containment'],native_decision_path=A['native_decision_path'],remote_selectors_enabled=False)
save(H/'workflow.json',workflow)
source_ancestry={}
for key,item in A['sources'].items():
    previous=read(OLD/'amendment.json')['sources'][key]
    source_ancestry[key]={'current':item,'ancestor':previous,'byte_equal':item['sha256']==previous['sha256']}
save(H/'source-ancestry.json',{'sources':source_ancestry,'original_frozen_unchanged':True})
(H/'selected-execution-plan.json').write_bytes(Path(A['execution_plan']['path']).read_bytes())
installation=read(H/'package/installation.json')
origins=[]
for p in sorted((H/'package/venv/Lib/site-packages').glob('okto_nexus*.dist-info/direct_url.json')):
    value=read(p)
    assert set(value).issubset({'url','archive_info','dir_info'})
    origins.append({'file':pin(p),'pip_origin':value})
save(H/'package/pip-origin-projection.json',{'scope':'Actual pip-installed origins, not rewritten to retained artifact identity.','origins':origins})
qualification={'status':'OFFLINE_REVISION16_QUALIFIED_NOT_EXECUTED','amendment_sha256':digest,
 'installation':pin(H/'package/installation.json'),'build':pin(H/'package/build-provenance.json'),
 'canonical_probe60':pin(H/'probe-qualification.json'),'composed_gate':pin(H/'gate-qualification.json'),
 'installed_native_provenance':{'passed':50,'new_source_cases':18,'existing_source_cases':32,'tool':'bcab2b','elapsed_seconds':186.63,
   'warnings':['One StarletteDeprecationWarning for testclient httpx; no product or fixture failure.'],'xml':pin(H/'checks/installed-native.xml'),
   'runner':pin(H/'checks/run_installed_native.py'),'origins':pin(H/'checks/installed-native-origins.json'),
   'fixtures':pin(H/'checks/fixture-pins.json'),'repository_source_imports':False,
   'scope':'Actual new installed Nexus/Core imports with copied fixture-only dependencies. No native/provider execution.'},
 'composition_delta':{'passed':6,'tool':'046f9a','xml':pin(H/'checks/composition.xml'),
   'runner':pin(H/'checks/run_composition.py'),'test_source':pin(H/'checks/test_composition.py')},
 'controller_delta':pin(H/'controller-qualification/qualification.json'),'controller_runtime_freeze':pin(H/'controller-qualification/runtime-freeze.json'),
 'suite_counts_not_summed_as_distinct':True,'ruff_F':{'tool':'016c9c','result':'PASS'},
 'root_review':{'context_entry_close':'d82a2d PASS','connector_zip_equivalence':'5cdc4a,132 ZIP entries equal including RECORD'},
 'preparation_antecedent':{'tool':'698e4f','failure':'Freeze helper accepted Path but received str during first source hash check; corrected Path conversion. No freeze emitted, runtime effect or test rerun.'},
 'connector_artifact_reuse':{'final_retained_sha256':'f9864f13db4c5e6e5afdfd8f28ca5384512a17a1f8efb1897cb3a4d810d43cf4',
   'actual_initial_pip_zip_sha256':'e1d1046d7bddfbaa116669e937430770ac1876278f192923614dc855d68e36aa',
   'installed_payloads_verified_excluding_record':131,'installed_payloads_changed':False,'pip_reexecuted':False,
   'initial_installation':pin(H/'package/initial-installation.json'),'initial_build':pin(H/'package/initial-build-provenance.json'),
   'actual_pip_origin_projection':pin(H/'package/pip-origin-projection.json'),
   'limitation':'Initial builder rebuilt unchanged Connector commit; final artifact reuses prior immutable ZIP after byte-equivalence proof. Initial actual pip wheel identity remains explicit; no claim pip installed the retained ZIP.'},
 'reused_unchanged_qualification':{'predecessor':pin(OLD/'qualification.json'),
   'scope':'Lifecycle/upgrade/grant transport, CLI readiness5 and prior preflight tests unchanged; only current context/history/policy/provenance deltas qualified here.'},
 'policy':A['policy'],'observation_bounds':A['observation_bounds'],'python':installation['python'],'python_flags':['-B','-I','-X','utf8'],
 'services_started':0,'provider_calls':0,'upgrade_actions':0,'grant_changes':0,'new_model_reservations':0,
 'acceptance_promoted':False,'remote_execution_enabled':False,
 'historical_control_receipt':'SUBMITTED snapshot retained; neither old decision nor control is replayed; target cancellation does not settle its control receipt.'}
save(H/'qualification.json',qualification)
(H/'README.md').write_text('''Revisão16 — preparação offline finita

Fonte Nexusb90e6824, Core7810/d881 e Connector645d/f986. Pacote próprio,1002payloads;
probe canônico60 passou em0,770s.50 testes de autoridade nativa instalada,6 testes
da composição e14 deltas do controlador ficam separados, sem somar sobreposições.
O builder recompôs inicialmente Connector;131payloads instalados (sem RECORD)
foram comparados ao ZIPf986 anterior e revalidados, sem reinstalação ou mutação
de payload. O ZIP realmente instalado e direct_url continuam documentados.

Carry341276/13, quatro novos IDs, máximo17, preventiva500k/tolerância700k;
158724 até preventiva e358724 até tolerância, sem garantia de conclusão.
Oito registros máximos (4 históricos+4novos): snapshot1/init2/margem1,
poll19/fresh20/cadence24/alvo200ms; deadline600 e readiness5 permanecem.
São limites operacionais, não novos critérios R3.

Local útil14 em nova sessão, continuação15 somente após sucesso/settlement
canônico na mesma sessão. Remoto16/17 permanece bloqueado. A antiga continuação14
da revisão15 não é elegível; decisão nativa antiga e interrupt não são reexecutados.
Request13 CANCELLED, recibo interrupt SUBMITTED e falhas históricas preservados.

Roteiro workflow.json: prepare, upgrade-plan, seleção técnica exata, upgrade-apply,
install/start único45s, observação passiva180s quando permitida, watcher de3handles,
review de grant/apply somente expirado e selecionado, útil14/continuação15 condicional,
stop normal, cleanup, uninstall, finalpresence, closure direto. Native decision:
private/native-decision.json, somente decisão real revisada. Contenção normal
turn.interrupt exata se stop45 continuar draining, sem força/novo turno/replay.
Cancelamento/cleanup não implicam conclusão do recibo interrupt ou billing final.

Nenhum serviço, modelo, grant ou migração foi executado nesta preparação.
''',encoding='utf-8',newline='\n')
names=('amendment.json','commands.json','workflow.json','qualification.json','README.md','selected-execution-plan.json',
 'technical-predecessor.json','source-ancestry.json','historical-grants.json','build_packages.py','reuse_connector_wheel.py',
 'probe_new_package.py','probe-qualification.json','compose_revision16.py','adapt_owned_sources.py','prepare_composer.py',
 'prepare_checks.py','check_composed_gate.py','gate-qualification.json','freeze_revision16.py',
 'package/build-provenance.json','package/installation.json','package/initial-build-provenance.json','package/initial-installation.json',
 'package/pip-origin-projection.json','package/dependency-manifest.json','package/prepare_dependencies.py','package/install_packages.py',
 'checks/run_installed_native.py','checks/installed-native.xml','checks/installed-native-origins.json','checks/fixture-pins.json',
 'checks/test_composition.py','checks/run_composition.py','checks/composition.xml')
paths=[H/name for name in names]+[Path(p['path']) for p in A['sources'].values()]
paths+=sorted(p for p in (H/'controller-qualification').rglob('*') if p.is_file() and p.suffix in ('.json','.py','.xml','.md'))
paths=list(dict.fromkeys(paths))
assert not any((H/name).exists() for name in ('public','private','runtime-private'))
manifest={'status':'FROZEN_OFFLINE_QUALIFIED_FINAL_ROOT_REVIEW_REQUIRED','amendment_sha256':digest,
 'files':{str(p.relative_to(H)).replace('\\','/'):pin(p) for p in paths},'no_runtime_effects':True,'remote_selectors_enabled':False}
save(H/'runtime-freeze.json',manifest)
save(H/'public-allowlist.json',{'files':[*manifest['files'].values(),pin(H/'runtime-freeze.json')],
 'excluded':['private','runtime-private','venv','wheels','sourcearchives','auth','transcripts','ownershiptoken/nonce'],
 'fixture_sources':'checks/fixture-pins.json retains exact copied source hashes; no product source imports in installed tests.'})
print(json.dumps({'amendment_sha256':digest,'freeze_sha256':sha(H/'runtime-freeze.json'),'qualification_sha256':sha(H/'qualification.json'),
 'allowlist_sha256':sha(H/'public-allowlist.json'),'workflow_sha256':sha(H/'workflow.json'),'files':len(paths)}))
