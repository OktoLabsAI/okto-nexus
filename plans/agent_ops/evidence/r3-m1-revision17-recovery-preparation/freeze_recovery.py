from pathlib import Path
import ast,hashlib,json,xml.etree.ElementTree as ET
H=Path(__file__).resolve().parent;OLD=H.with_name('work-revision17')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8',newline='\n')
A=read(H/'amendment.json');digest=sha(H/'amendment.json')
assert read(H/'gate-qualification.json')['amendment_sha256']==digest
for item in A['sources'].values():
    assert sha(item['path'])==item['sha256'];ast.parse(Path(item['path']).read_text(encoding='utf-8-sig'))
suites=list(ET.parse(H/'checks/recovery.xml').getroot().iter('testsuite'))
assert sum(int(s.get('tests',0)) for s in suites)==6
assert not sum(int(s.get('errors',0))+int(s.get('failures',0)) for s in suites)
workflow=read(OLD/'workflow.json')
for step in workflow['steps']:
    step['argv']=[arg.replace(str(OLD),str(H)) for arg in step['argv']]
    step['argv'][step['argv'].index('--expected-amendment-sha256')+1]=digest
    assert 'upgrade' not in step['argv']
workflow.update(amendment_sha256=digest,native_decision_path=A['native_decision_path'],recovery_plan=A['recovery_plan'],
 closed_preflight=A['closed_preflight'],same_paid_policy_and_ids=True,
 scope='Fresh operational namespace after closed pre-review failure. Same W16 package, paid basis, policy17 and unselected local15/16; no old invocation replay.')
save(H/'workflow.json',workflow)
previous=read(OLD/'amendment.json')
ancestry={k:{'current':v,'ancestor':previous['sources'][k],'byte_equal':v['sha256']==previous['sources'][k]['sha256']} for k,v in A['sources'].items()}
save(H/'source-ancestry.json',{'sources':ancestry,'original_frozen_unchanged':True,
 'changed_keys':[k for k,v in ancestry.items() if not v['byte_equal']]})
assert [k for k,v in ancestry.items() if not v['byte_equal']]==['context','authorize','fresh_work_controller']
qualification={'status':'OFFLINE_RECOVERY_QUALIFIED_NOT_EXECUTED','amendment_sha256':digest,
 'recovery_plan':A['recovery_plan'],'closed_preflight':A['closed_preflight'],'base_qualified_freeze':pin(OLD/'runtime-freeze.json'),
 'base_qualification':pin(OLD/'qualification.json'),'reused_installation':A['installation'],
 'delta':{'passed':6,'elapsed_seconds':7.32,'tool':'1b05c1','xml':pin(H/'checks/recovery.xml'),
   'test_source':pin(H/'checks/test_recovery.py'),'runner':pin(H/'checks/run_recovery.py'),
   'scope':'Actual recovery gate/paid derivation/closure, actual installed TerminalAuthorization.authorization_review plus TerminalWork.api and bounded transport, submitted/unknown/tampered review refused, changed predecessor request refused.'},
 'antecedent':{'passed':5,'fixture_failures':1,'tool':'0fccd2','xml':pin(H/'checks/initial-5pass-1fixture-fail.xml'),
   'cause':'Fixture bypassed installed TerminalWork.api prefix; fence correctly refused path. Fixture now uses actual installed api method. No production change; overlapping runs not summed.'},
 'gate':pin(H/'gate-qualification.json'),'gate_tool':'eccc1a',
 'controller_namespace_delta':pin(H/'controller-qualification/qualification.json'),
 'controller_runtime_freeze':pin(H/'controller-qualification/runtime-freeze.json'),
 'reused_without_rerun':{'base_controller12':pin(OLD/'controller-qualification/qualification.json'),
   'base_composition10':pin(OLD/'qualification.json'),'quote_fixture':pin(OLD/'checks/quote-qualification.json'),
   'installed50_and_probe60':A['reused_package']['qualification']},
 'source_delta_keys':['context','authorize','fresh_work_controller'],'unchanged_sources':24,
 'root_review':{'context_guard':'5c971b PASS','controller_namespace':'f430e9/043dc9 PASS'},
 'policy_unchanged':A['policy'],'paid_basis_unchanged':{k:A['basis'][k] for k in ('checkpoint','companion','accounting')},
 'original_failed_preflight_retained':True,'old_fault_reset_or_mutated':False,'new_paid_allocation':False,
 'builds':0,'pip_runs':0,'probe_runs':0,'services_started':0,'provider_calls':0,'authorization_calls_real':0,
 'new_model_reservations':0,'remote_execution_enabled':False,'acceptance_promoted':False,
 'historical_fault_semantics':'Original W17 AUTHORIZATION_MAINTENANCE_UNCONFIRMED remains in immutable checkpoint/closure referenced by mandatory operational_preflight source pin. New controller derives same W16 paid basis; no fabricated settlement/refund or original fault edit.'}
save(H/'qualification.json',qualification)
(H/'README.md').write_text('''Recuperação operacional da revisão17 — offline

Não é novo ciclo pago nem revisão18. Mesma policy17:460793/14 históricos,
preventiva600k/tolerância700k, máximo18; IDs local15/16 nunca reservados,
remoto17/18 bloqueado. Pacote W16 e prompt exato permanecem iguais.

W17 anterior foi fechado normalmente: calls{},requests{}, fault original
AUTHORIZATION_MAINTENANCE_UNCONFIRMED, três saídas físicas0 e tarefas ausentes.
Esses artefatos/pins e inventário finito são guard obrigatório; não são apagados,
reescritos ou tratados como trabalho resolvido. Derivação continua da mesma base
paga W16 com cinco históricos; o preflight falho é histórico operacional separado.

Única correção funcional: helper aceita somente revisão histórica state=review
exata, pin/revision/scope íntegros. O método instalado cria novo POST canônico
review e salva a nova revisão; o helper não edita checkpoint. Submitted/unknown
continuam recusados. Emissão continua exigindo nova revisão canônica expirada e
seleção CAS exata; nenhuma chamada real nesta preparação.

6 testes focais finais PASS,2 testes namescope do controlador separados;12controller,
10composition/quote e50installed/probe60 anteriores reutilizados sem rerun.
Antecedente5PASS/1fixtureFAIL de prefixoAPI retido, corrigido usando TerminalWork.api
instalado. Somente context/authorize/Freshpath diferem;24fontes byteiguais.

workflow.json usa namespace novo e único; sem migração/build/grant/modelo durante
preparação. Contenção normal existente permanece, sem force. Não houve aceite M1.
''',encoding='utf-8',newline='\n')
names=['amendment.json','recovery-plan.json','closed-preflight.json','workflow.json','source-ancestry.json',
 'qualification.json','README.md','compose_recovery.py','freeze_recovery.py','check_composed_gate.py','gate-qualification.json',
 'checks/test_recovery.py','checks/run_recovery.py','checks/recovery.xml','checks/initial-5pass-1fixture-fail.xml']
paths=[H/n for n in names]+[Path(v['path']) for v in A['sources'].values()]
paths+=sorted(p for p in (H/'controller-qualification').rglob('*') if p.is_file() and p.suffix in ('.py','.json','.xml','.md'))
paths=list(dict.fromkeys(paths));assert not any((H/n).exists() for n in ('public','private','runtime-private','package'))
manifest={'status':'FROZEN_OFFLINE_RECOVERY_FINAL_ROOT_REVIEW_REQUIRED','amendment_sha256':digest,
 'files':{str(p.relative_to(H)).replace('\\','/'):pin(p) for p in paths},'no_runtime_effects':True,'same_paid_policy_and_ids':True,'remote_selectors_enabled':False}
save(H/'runtime-freeze.json',manifest)
save(H/'public-allowlist.json',{'files':[*manifest['files'].values(),pin(H/'runtime-freeze.json')],
 'excluded':['private','runtime-private','venv','wheels','auth','transcripts','rawcontroller'],'reused_proofs_are_external_pins':True})
print(json.dumps({'files':len(paths),**{k:sha(H/n) for k,n in {'amendment':'amendment.json','freeze':'runtime-freeze.json',
 'qualification':'qualification.json','allowlist':'public-allowlist.json','workflow':'workflow.json'}.items()}}))
