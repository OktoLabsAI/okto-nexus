"""Read-only reconciliation of SVC-T26 and SVC-T28; no product imports/tests."""
import ast
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT=Path(__file__).parent
REPOS={'nexus':ROOT,'connector':ROOT.parent/'okto-nexus-connector'}
E='plans/agent_ops/evidence/'
inputs={}
def sha(b): return hashlib.sha256(b).hexdigest()
def ref(path,repository='nexus',**details):
    raw=(REPOS[repository]/path).read_bytes()
    item=dict(repository=repository,path=path,sha256=sha(raw),bytes=len(raw))
    inputs[(repository,path)]=item
    return item|details
def read(path):
    ref(path)
    return json.loads((ROOT/path).read_text(encoding='utf-8'))
def source(path,name,repository='nexus'):
    raw=(REPOS[repository]/path).read_text(encoding='utf-8')
    nodes=[n for n in ast.walk(ast.parse(raw)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==name]
    assert len(nodes)==1,(path,name,len(nodes))
    n=nodes[0]
    return ref(path,repository,symbol=name,line=n.lineno,end_line=n.end_lineno,
               function_sha256=sha(ast.get_source_segment(raw,n).encode('utf-8')),
               assertions=[dict(line=x.lineno,expression=ast.unparse(x.test)) for x in ast.walk(n) if isinstance(x,ast.Assert)],
               exception_oracles=[dict(line=x.context_expr.lineno,expression=ast.unparse(x.context_expr)) for x in ast.walk(n) if isinstance(x,ast.withitem) and isinstance(x.context_expr,ast.Call) and ast.unparse(x.context_expr.func).endswith('.raises')])
def test(path,name,report,classname,repository='nexus',mode='injected_contract'):
    cases=[c for c in ET.parse(ROOT/report).findall('.//testcase') if c.get('classname')==classname and (c.get('name')==name or c.get('name','').startswith(name+'['))]
    assert cases,(report,classname,name)
    assert all(not any(c.find(k) is not None for k in ['failure','error','skipped']) for c in cases),(report,name)
    return dict(source=source(path,name,repository),report=ref(report),qualification_mode=mode,
                nodes=[dict(node_id=c.get('classname')+'::'+c.get('name'),status='PASS') for c in cases])

ledger=read('plans/agent_ops/ledger.json')
audit=read(E+'r3-task-reconciliation/svc/audit.json')
plan='PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
planref=ref(plan)
literals={}
for i,line in enumerate((ROOT/plan).read_text(encoding='utf-8').splitlines(),1):
    m=re.match(r'^\|\s*(SVC-T(?:26|28))\s*\|\s*(.*?)\s*\|$',line)
    if m:literals[m[1]]=(i,m[2])
assert set(literals)=={'SVC-T26','SVC-T28'}
for k,(_,text) in literals.items():assert ledger['scenarios'][k]['requirement']==text

UP=E+'pr02-upgrade-installed.xml'
upgrade_tests=[]
for repo,path,cls in [('nexus','tests/test_service_upgrade.py','tests.test_service_upgrade'),
                      ('connector','tests/unit/test_service_upgrade.py','tests.test_connector_service_upgrade')]:
    for name in ['test_every_persistence_boundary_can_resume_same_plan',
                 'test_lost_native_response_keeps_fence_and_recognizes_only_exact_effect',
                 'test_user_edit_after_lost_response_is_not_adopted',
                 'test_downgrade_and_unconfirmed_existing_runtime_are_refused',
                 'test_context_edit_during_interruption_is_preserved']:
        upgrade_tests.append(test(path,name,UP,cls,repo))
upgrade_tests += [test('tests/test_service_upgrade_process.py','test_reviewed_upgrade_between_installed_environments_preserves_database',UP,'tests.test_service_upgrade_process',mode='real_installed_environment_and_process'),
                 test('tests/integration/test_service_upgrade_process.py','test_reviewed_upgrade_between_installed_environments_preserves_journal',UP,'tests.test_connector_service_upgrade_process','connector','real_installed_environment_and_process')]
all_upgrade=ET.parse(ROOT/UP).findall('.//testcase')
assert len(all_upgrade)==200 and all(not any(c.find(k) is not None for k in ['failure','error','skipped']) for c in all_upgrade)

SV=E+'r3-cooperative-drain/installed/nexus-installed-v1/canonical/tests.xml'
foreground_tests=[test('tests/integration/test_windows_job_daemon.py','test_daemon_under_restrictive_job',E+'pr02-connector-user-service.xml','tests.integration.test_windows_job_daemon','connector','real_Windows_Job_Object_and_process'),
    test('tests/execution_r4/test_server_signal_shutdown.py','test_signal_keeps_serve_process_and_http_until_inventory_release',SV,'tests.execution_r4.test_server_signal_shutdown',mode='real_installed_foreground_process_managed_by_external_test_parent'),
    test('tests/test_user_service_installation.py','test_supervised_entry_is_foreground_fenced_and_uses_saved_context',SV,'tests.test_user_service_installation',mode='injected_run_serve_wrapper_contract'),
    test('tests/test_user_service_installation.py','test_foreground_refuses_installed_integration_before_bootstrap',SV,'tests.test_user_service_installation',mode='injected_installation_conflict_contract')]

rows=[dict(id='SVC-T26',literal_requirement=literals['SVC-T26'][1],plan_line=literals['SVC-T26'][0],
    status_read=ledger['scenarios']['SVC-T26']['status'],proposed_status='VERIFIED',
    rationale='O literal exige recuperação documentada de upgrade interrompido sem downgrade destrutivo; não exige executar um downgrade histórico nem mutar Task Scheduler real. Os dois hosts retomam o mesmo plano após cada fronteira persistida, aceitam resposta nativa perdida só pelo efeito exato, recusam downgrade e preservam DB/journal nos upgrades instalados reais.',
    evidence=upgrade_tests,
    implementation=[ref('src/okto_nexus/service_upgrade.py'),ref('src/okto_nexus/adapters/outbound/service_manager/upgrade.py'),
                    ref('src/okto_nexus_connector/platform/service_upgrade.py','connector')],
    documentation=[ref('docs/service-lifecycle.md',line=304,end_line=318),ref('docs/service-lifecycle.md','connector',line=195,end_line=209),ref(E+'pr02-upgrade.md'),ref(E+'pr02-upgrade-wheels.json')],
    installed_campaign=dict(report=ref(UP),passed=200,failed=0,errors=0,skipped=0,not_additive_with_selected_nodes=True),
    documented_recovery='Preservar plano/ambiente antigo/documentos; repetir upgrade-apply com o mesmo arquivo/revisão; SERVICE_UPGRADE_PENDING bloqueia start. Efeito nativo incerto exige comparação exata, mudanças alheias permanecem conflito. Upgrade não migra a base; downgrade binário é recusado.',
    stale_remaining='No historical schema binary downgrade recovery or real task upgrade claimed é limite honesto, não pendência do literal SVC-T26.',
    specific_pending_for_literal=None,
    limit='Windows e ambientes descartáveis instalados. Interrupções e resposta de Task Scheduler são injetadas; dois upgrades de ambientes/processos são reais. Não prova atualização nativa de tarefa, migração histórica cruzada, rollback após migração, login/reboot, POSIX ou trabalho produtivo.'),
dict(id='SVC-T28',literal_requirement=literals['SVC-T28'][1],plan_line=literals['SVC-T28'][0],
    status_read=ledger['scenarios']['SVC-T28']['status'],proposed_status='VERIFIED',
    rationale='A alternativa supervisor externo é atendida no escopo Windows: Connector fica foreground dentro de Job Object real restritivo, e Nexus executa run_serve instalado em processo real mantido/controlado por um pai externo de teste. A evidência real Nexus é própria; não deriva da prova Connector. Código usa o mesmo owner foreground, enquanto contratos separados recusam concorrência com integração instalada.',
    evidence=foreground_tests,
    implementation=[source('src/okto_nexus/adapters/inbound/cli/serve.py','run_serve'),source('src/okto_nexus/adapters/inbound/cli/runtime_server.py','RuntimeServer'),
                    source('src/okto_nexus/adapters/inbound/cli/supervised_service.py','run'),
                    source('src/okto_nexus_connector/daemon/manager.py','run_foreground','connector')],
    documentation=[ref('docs/service-lifecycle.md',line=3,end_line=24),ref('docs/service-lifecycle.md',line=104,end_line=127),ref('docs/service-lifecycle.md','connector',line=27,end_line=31),ref('docs/service-lifecycle.md','connector',line=74,end_line=77),ref(E+'r3-cooperative-drain/qualification.json')],
    component_scopes={
       'connector':dict(real='Job Object Windows com KILL_ON_JOB_CLOSE, sem permissão de breakaway. Foreground fica ready, para via IPC e o processo retorna 0; tentativa detached é recusada com orientação daemon run. Nenhum Task Scheduler é registrado.',
                        retained_nodes=2),
       'nexus':dict(real='Popen de Python -I chama o run_serve instalado diretamente. O pai espera healthz e envia SIGINT/SIGTERM ao filho por controlador de stdin; processo/HTTP permanecem até liberar o owner. Saída 0 e único executor embedded DISCONNECTED são conferidos. Não há start/daemon intermediário nessa composição.',
                   injected='Discovery é sintético e a liberação de inventory é bloqueada/injetada; HTTP, processo, sinais e run_serve/RuntimeServer são reais. O teste de wrapper run_supervised usa Mock de run_serve e NÃO é usado sozinho como prova runtime.',
                   retained_real_nodes=4)},
    interpretation='Supervisor externo mínimo aqui significa o processo pai de teste que cria, acompanha, sinaliza e junta o Server foreground real. Não significa que Task Scheduler, Docker, Kubernetes, systemd ou outro produto específico foi qualificado.',
    no_double_supervision_basis='Nexus run_serve toma o lock e chama RuntimeServer.run no processo foreground; pai real continua observando esse processo até o encerramento. Wrapper chama foreground uma vez e entrada foreground recusa integração instalada concorrente. Connector run_foreground e Job Object exercitam a alternativa operacional sem detached. Watchdog de recursos nativos, quando existente, não é apresentado como segundo Server/supervisor de serviço.',
    stale_remaining='A prova real de foreground Nexus estava fora do E10 antigo; restringir T28 a POSIX/container ou exigir registro real de tarefa acrescentaria uma condição não literal à alternativa de supervisor externo já observada.',
    specific_pending_for_literal=None,
    limit='Verificado somente no escopo externo Windows descrito, não em container nem POSIX. Não prova políticas de restart/logon de um supervisor instalado. A prova de conflito/wrapper do Task Scheduler é injetada e assim permanece rotulada; não é promovida a registro nativo real.')]
report=dict(format='r3.svc-two-scenario-reconciliation',version=1,base_head='4855abd56ae4733a3e0445d835a085a697dda1df',
    plan=planref,scope=['SVC-T26','SVC-T28'],scenarios=rows,
    historical_audit=ref(E+'r3-task-reconciliation/svc/audit.json',locator='scenarios[id=SVC-T26 or SVC-T28]'),
    tests_executed=0,product_imports=False,checkout_edits=False,ledger_edits=False,
    method='Read source, documentation and exact retained XML PASS nodes; no new campaign or runtime execution.',
    acceptance='No M1/M2/R3 or untested platform promotion; these are scoped literal scenario recommendations.')

def write(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
write('matrix.json',report)
write('input-manifest.json',dict(files=sorted(inputs.values(),key=lambda x:(x['repository'],x['path']))))
summary='''# SVC-T26 / SVC-T28 — proposta literal finita

Recomendo **VERIFIED para ambos**, somente nos escopos descritos na matriz. Nenhum status foi editado.

- **SVC-T26:** os dois hosts têm retomada do mesmo plano em cada fronteira de persistência, resposta nativa perdida, recusa de downgrade e upgrades reais de ambientes instalados preservando DB/journal. O relatório instalado retém 200 PASS. Recuperação é documentada como repetir o mesmo arquivo/revisão; não exige executar downgrade histórico nem atualizar uma tarefa Windows real.
- **SVC-T28:** Connector tem dois PASS reais sob Job Object Windows restritivo (detached recusado; foreground funciona). Nexus possui quatro PASS instalados próprios: processo foreground real iniciado, observado, sinalizado e unido por um pai externo de teste, com HTTP/owner mantidos até shutdown. O wrapper supervisionado com Mock é evidência contratual separada, não substituto desse processo real.

Para T28, “supervisor externo” significa precisamente esse pai que controla a vida do processo foreground. Nenhum produto de supervisão específico é qualificado. Não há requisito adicional de POSIX/container quando essa alternativa foi observada. Caso o ledger queira uma campanha de Docker/Task Scheduler, mantenha-a como subscope distinto e não como pendência literal genérica destes dois cenários.

Limites: Windows/local; nenhum registro de tarefa, container, login/reboot, provedor pessoal ou nova execução. Interrupções do upgrade e efeitos de Task Scheduler são injetados. Os dois upgrades instalados e os processos foreground são reais. Os XMLs históricos não são rotulados como execução do wheel atual; Nexus foreground usa a qualificação instalada SVC-07 já retida.

matrix.json contém literal, implementação, assertions, nodes PASS, SHA e limites separados por componente. input-manifest.json e artifact-manifest.json delimitam o pacote público.
'''
(OUT/'summary.md').write_text(summary,encoding='utf-8')
changed=[repo+':'+path for (repo,path),item in inputs.items() if sha((REPOS[repo]/path).read_bytes())!=item['sha256']]
assert not changed,changed
nodes={(t['report']['path'],n['node_id']) for row in rows for t in row['evidence'] for n in t['nodes']}
write('verification.json',dict(literal_matches=2,selected_retained_report_node_pairs=len(nodes),input_files_unchanged=len(inputs),new_tests_run=0,checkout_edits=False))
names=['matrix.json','summary.md','input-manifest.json','verification.json','reconcile.py']
write('artifact-manifest.json',dict(public_allowlist=names,files=[dict(path=n,sha256=sha((OUT/n).read_bytes()),bytes=(OUT/n).stat().st_size) for n in names],excludes=['DB','private state','credentials','venv']))
print(json.dumps(dict(path=str(OUT),proposed_statuses={x['id']:x['proposed_status'] for x in rows},selected_retained_report_node_pairs=len(nodes),inputs=len(inputs),matrix_sha256=sha((OUT/'matrix.json').read_bytes()),manifest_sha256=sha((OUT/'artifact-manifest.json').read_bytes())),indent=2))
