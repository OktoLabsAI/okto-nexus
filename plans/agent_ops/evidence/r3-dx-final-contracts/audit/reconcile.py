"""Finite read-only review of the explicitly selected remaining DX scenarios."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT=Path(__file__).parent
REPOS={'nexus':ROOT,'connector':ROOT.parent/'okto-nexus-connector','core':ROOT.parent/'okto-nexus-connector-core'}
E='plans/agent_ops/evidence/'
CAT=E+'r3-task-reconciliation/dx/matrix.json'
IDS=[f'DX-T{i:02}' for i in [27,29,30,31,33,34,35,36,*range(38,51)]]
inputs={}
def sha(data):return hashlib.sha256(data).hexdigest()
def ref(path,repository='nexus',**extra):
    repository=repository.lower()
    raw=(REPOS[repository]/path).read_bytes()
    value=dict(repository=repository,path=path,sha256=sha(raw),bytes=len(raw))
    inputs[(repository,path)]=value
    return value|extra
def read(path):
    ref(path)
    return json.loads((ROOT/path).read_text(encoding='utf-8'))
ledger=read('plans/agent_ops/ledger.json')
catalog={t['id']:t for t in read(CAT)['tasks']}
plan='PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
planref=ref(plan)
literals={}
for i,text in enumerate((ROOT/plan).read_text(encoding='utf-8').splitlines(),1):
    m=re.match(r'^\|\s*(DX-T\d{2})\s*\|\s*(.*?)\s*\|$',text)
    if m and m[1] in IDS:literals[m[1]]=(i,m[2])
assert set(literals)==set(IDS)

def function(path,name,repository='nexus'):
    raw=(REPOS[repository]/path).read_text(encoding='utf-8')
    nodes=[n for n in ast.walk(ast.parse(raw)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    assert len(nodes)==1,(path,name,len(nodes))
    n=nodes[0]
    return ref(path,repository,symbol=name,line=n.lineno,end_line=n.end_lineno,
               function_sha256=sha(ast.get_source_segment(raw,n).encode('utf-8')),
               assertions=[dict(line=x.lineno,expression=ast.unparse(x.test)) for x in ast.walk(n) if isinstance(x,ast.Assert)],
               exception_oracles=[dict(line=x.context_expr.lineno,expression=ast.unparse(x.context_expr)) for x in ast.walk(n) if isinstance(x,ast.withitem) and isinstance(x.context_expr,ast.Call) and ast.unparse(x.context_expr.func).endswith('.raises')])
def test(path,name,report,repository='nexus',classname=None):
    classname=classname or path[:-3].replace('/','.')
    matches=[x for x in ET.parse(ROOT/report).findall('.//testcase') if x.get('classname')==classname and (x.get('name')==name or x.get('name','').startswith(name+'['))]
    assert matches,(report,classname,name)
    assert all(not any(x.find(k) is not None for k in ['failure','error','skipped']) for x in matches),(report,name)
    return dict(source=function(path,name,repository),report=ref(report),
                passed_nodes=[x.get('classname')+'::'+x.get('name') for x in matches],
                reading='Retained XML only; no new execution by this audit.')
def prod(tasks):
    sources={}
    for ident in tasks:
        for s in catalog[ident]['sources']:
            v=ref(s['path'],s['repository'],symbol=s.get('symbol'),retained_line=s.get('line'),retained_catalog_sha256=s['sha256'])
            v['same_bytes_as_catalog']=v['sha256']==s['sha256']
            sources[(v['repository'],v['path'],v['symbol'])]=v
    return list(sources.values())

WORK='tests/execution_r4/test_terminal_work.py'
CONNECT='tests/execution_r4/test_terminal_connect.py'
IDENT='tests/execution_r4/test_terminal_identity.py'
POLICY='tests/execution_r4/test_terminal_policy.py'
DIAG='tests/execution_r4/test_project_diagnostics.py'
CR='tests/unit/test_connect_project_review.py'
REUSE='tests/unit/test_connect_reuse.py'
TW=E+'pr03-terminal-work-installed.xml'
TP=E+'pr03-terminal-policy-installed.xml'
RB=E+'pr03-remote-bootstrap/candidate-v1/nexus/installed.xml'
RB3=E+'pr03-remote-bootstrap/candidate-v3/nexus/installed.xml'
CB=E+'pr03-remote-bootstrap/candidate-v1/connector/installed.xml'
RENEW=E+'pr03-remote-renewal/candidate-v2/nexus/installed.xml'
DI=E+'pr03-project-doctor-installed.xml'
PE=E+'pr03-preset-evolution-installed.xml'
rows=[]
COMMON='Windows/local, fontes e XML instalados já retidos; testes de protocolo/SQLite/Core e peers sintéticos não são inferência nem qualificação de provedor real. Nenhuma nova execução nesta auditoria.'

def row(number,tasks,reason,tests,limit,extra=(),pending=None,keep='IN_PROGRESS',verified_subscopes=()):
    ident=f'DX-T{number:02}'
    line,literal=literals[ident]
    old=ledger['scenarios'][ident]
    assert old['requirement']==literal,ident
    rows.append(dict(id=ident,literal_requirement=literal,plan_line=line,current_status=old['status'],
         proposed_status='VERIFIED' if pending is None else keep,reason=reason,
         implementation=prod(tasks),related_tasks=tasks,tests=tests,evidence=list(extra),
         specific_pending=pending,pending_kind=None if pending is None else ('retained_targeted_proof_missing' if number==44 else 'real_campaign_not_run'),
         verified_subscopes=list(verified_subscopes),limit=limit,common_limit=COMMON,
         acceptance_effect='No M1/M2/R3 or unqualified platform promotion.'))

row(27,['DX-14','DX-19'],
    'Workspace canônico remoto é separado do diretório físico do Connector. O host resolve referências aprovadas em seu vault e HOME antes do Core; o operador não substitui esses dados por seu próprio diretório/credencial.',
    [test('tests/unit/test_configure.py','test_local_wizard_reuses_remote_workspace_with_independent_folder',CB,'connector'),
     test('tests/unit/test_launch_configuration.py','test_default_owner_uses_approved_references_and_real_core_prepare',E+'pr03-remote-preset-connector-installed.xml','connector'),
     test('tests/unit/test_launch_configuration.py','test_host_approved_environment_qualifies_once_after_materialization',E+'pr03-remote-preset-connector-installed.xml','connector'),
     test('tests/execution_r4/test_remote_setup_integration.py','test_operator_and_connector_cli_complete_same_root_once',RB)],
    'Contrato de seleção/materialização do host com diretórios temporários e secret resolver sintético. Não certifica login/provedor nem a configuração efetiva consumida por processo real (T43), nem transporte entre duas máquinas físicas.',
    [ref('src/okto_nexus_connector/services/launch_configuration.py','connector')])
row(29,['DX-16'],
    'Uma instalação detectada gera candidato/recomendação estável com projeto/defaults no mesmo review, sem executar o binário ou perguntar inicialmente por transporte MCP/runtime.',
    [test(CR,'test_one_detected_installation_is_recommended_without_executing_or_prompting',CB,'connector'),test(CR,'test_one_project_review_submits_existing_canonical_defaults',CB,'connector'),test(CR,'test_connect_entry_reaches_one_review_with_current_folder_and_complete_installation',CB,'connector'),test(IDENT,'test_default_cli_review_is_stable_and_reconnect_preserves_identity_customizations',TP)],
    'Seleção e UX são predicados contratuais exercitados com inventário sintético; não se promove presença em PATH a login/qualificação.')
row(30,['DX-16'],
    'Ambiguidade material pergunta uma vez e preserva a instalação exata. Descoberta retorna versão/qualificação ainda desconhecidas; doctor mantém prontidão/login/prova de trabalho separados.',
    [test(CR,'test_material_ambiguity_asks_once_and_preserves_exact_candidate',CB,'connector'),test(CR,'test_one_detected_installation_is_recommended_without_executing_or_prompting',CB,'connector'),test(DIAG,'test_ready_connection_does_not_prove_provider_login_participation_or_work',DI)],
    'Não exige provedor real para provar a ausência de inferência indevida de PATH; não qualifica os candidatos sintéticos.')
row(31,['DX-15','DX-19'],
    'CLI conclui review/approve/Finish usando o setup existente e entra no trabalho apenas após o checkpoint configurado. A campanha do entrypoint instalado exercita start/reuse/stop sem browser; remoto usa o CLI do operador.',
    [test(CONNECT,'test_cli_plan_apply_and_reconnect_use_saved_profile',TW),test(CONNECT,'test_interactive_connect_enters_work_only_after_configuration',TW),test('tests/test_terminal_connect_process.py','test_connect_starts_reuses_and_leaves_service_owned_until_explicit_stop',TW),test('tests/execution_r4/test_remote_setup_integration.py','test_operator_and_connector_cli_complete_same_root_once',RB)],
    'Concluir setup pelo terminal é distinto de trabalho real completo T39/T40. Processo/CLI instalados reais e setup nativo sintético não fecham M1.')
row(33,['DX-17','DX-19'],
    'Connect persiste o mesmo setup antes dos efeitos; resposta perdida de probe/test/Finish recupera recibo sem novos efeitos. Bootstrap remoto recupera as mesmas referências e nunca reemite a chave.',
    [test(CONNECT,'test_response_loss_resumes_without_repeating_native_effects',TW),test(CONNECT,'test_submitted_test_with_lost_cache_is_not_replayed',TW),test('tests/test_remote_setup_server.py','test_lost_response_recovers_same_references_never_key_or_rotation',RB3),test('tests/execution_r4/test_remote_setup_integration.py','test_operator_and_connector_cli_complete_same_root_once',RB)],
    'Recovery do protocolo/objetos canônicos é comprovado; não exige tarefa de provedor para provar deduplicação do setup.')
row(34,['DX-07','DX-17'],
    'Doctor já mantém login/qualificação desconhecidos e não inicia probes. Isso não observa o comportamento de um harness real sem login iniciado pelo serviço.',
    [test(DIAG,'test_ready_connection_does_not_prove_provider_login_participation_or_work',DI),test(DIAG,'test_current_open_eligibility_does_not_run_another_probe_or_turn',DI)],
    'Não usar missing MCP credential, variável sintética ou refusal de peer como ausência de login do provedor real.',
    [ref(CAT,locator='tasks[id=DX-16 or DX-17].pending')],
    pending='Executar a campanha instalada com login do provedor ausente no host do serviço; reter instrução concreta emitida e prova de que o owner não fica bloqueado em prompt invisível, com cleanup. Nenhuma lacuna de produto específica foi demonstrada pela leitura.',keep='NOT_RUN',verified_subscopes=['diagnostic_proof_levels_and_passivity'])
row(35,['DX-07','DX-17'],
    'Checks independentes distinguem serviço/identidade, MCP initialize/list_tools, sessão READY e resultado/handoff. Nenhum nível intermediário implica participação/trabalho concluído.',
    [test(DIAG,'test_ready_connection_does_not_prove_provider_login_participation_or_work',DI),test(DIAG,'test_ready_session_open_is_not_a_productive_result',DI),test('tests/execution_r4/test_participant_doctor.py','test_actual_tcp_mcp_is_not_agent_participation_or_model_work',E+'pr04-participant-removal-installed.xml')],
    'VERIFIED é a separação/honestidade dos níveis; não certifica o provedor ausente.',
    [ref(E+'pr04-participant-guide/browser/browser-report.json')])
row(36,['DX-15','DX-18','DX-20'],
    'Plan/recusa não executam probe nem setup. Após aprovação explícita dos efeitos de conexão, Finish informa work_state=not_submitted; somente entrada explícita do usuário submete trabalho pelos serviços canônicos.',
    [test(CR,'test_decline_review_has_no_registration_probe_daemon_or_setup_state',CB,'connector'),test(IDENT,'test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key',TP),test(CONNECT,'test_interactive_connect_enters_work_only_after_configuration',TW),test(WORK,'test_interactive_cli_request_question_answer_result_and_return',TW)],
    'O teste de conexão potencialmente pago é um efeito separado mostrado no review e autorizado; não é tarefa/smoke produtivo automático. Peers sintéticos não são uso real do provedor.',
    [ref('src/okto_nexus/application/project_preset.py',symbol='effects'),ref('docs/terminal-connect.md')])
row(38,['DX-18','DX-19'],
    'Resumo único, criação autorizada e rollback/recovery estão provados. A pré-condição literal de instalação nova com harness/provedor prontos ainda foi modelada por candidatos/probes sintéticos.',
    [test(IDENT,'test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key',TP),test(IDENT,'test_late_finish_failure_rolls_back_identity_key_and_every_setup_object',TP),test('tests/execution_r4/test_remote_setup_integration.py','test_operator_and_connector_cli_complete_same_root_once',RB)],
    'Não exigir toda a campanha M1 para validar só o resumo; tampouco trocar prontidão real de harness/provedor por fixture.',
    [ref(CAT,locator='tasks[id=DX-16 or DX-18].pending')],
    pending='Qualificar a instalação nova instalada com harness/provedor efetivamente prontos, exibindo identidade/workspace/perfil no mesmo resumo e conferindo que a aprovação só cria os objetos autorizados, sem persona manual/dashboard. O contrato de revisão já está provado.',
    verified_subscopes=['single_review_and_defaults','authorized_atomic_identity_workspace_binding','same_root_recovery'])
row(39,['DX-20'],
    'Existe fluxo terminal completo com pergunta/resposta/resultado e retorno, mas sua execução usa peer nativo sintético. O literal pede trabalho real na rota local padrão instalada.',
    [test(WORK,'test_interactive_cli_request_question_answer_result_and_return',TW),test(WORK,'test_send_result_reopen_continue_and_close_share_canonical_session',TW)],
    'Não concatenar initialize, fake native e testes de configuração em uma campanha real.',
    [ref(E+'pr03-terminal-work.md'),ref(CAT,locator='tasks[id=DX-20].pending')],
    pending='Campanha M1 local instalada: trabalho real autorizado, acompanhamento, pergunta/permissão representativa, resposta, resultado correlacionado e continuação terminal; sem dashboard/config manual, com provider explicitamente autorizado.',keep='NOT_RUN',
    verified_subscopes=['canonical_terminal_work_contract_with_synthetic_peer'])
row(40,['DX-19','DX-20'],
    'Operador autenticado separado do host, aprovação/renovação e trabalho remoto canônico têm provas sintéticas; a mesma campanha real de T39 via Connector não foi executada.',
    [test('tests/execution_r4/test_remote_operator_terminal.py','test_remote_human_renews_and_answers_native_permission_without_agent_key',E+'pr03-remote-operator-installed.xml'),test('tests/execution_r4/test_remote_setup_integration.py','test_operator_and_connector_cli_complete_same_root_once',RB)],
    'HTTP/WebSocket/IPC reais e vault temporário não substituem provedor nativo real ou o percurso M1 remoto.',
    [ref(E+'pr03-remote-bootstrap/reports.json'),ref(E+'pr03-remote-renewal/reports.json')],
    pending='Executar M1 instalado via Connector com trabalho/provedor reais e pergunta/permissão resolvida pelo CLI autenticado do operador, provando ausência de credencial administrativa no host remoto e recusa de decisão pelo participante.',
    verified_subscopes=['operator_authority_separate_from_participant','remote_setup_and_renewal_real_protocol_synthetic_peer'])
row(41,['DX-17','DX-21'],
    'Reconnect recupera identidade/binding/grants e lê personalizações posteriores sem reemitir autoridade. Evolução opcional usa merge e Finish separado; defaults não reaplicam silenciosamente.',
    [test(IDENT,'test_default_cli_review_is_stable_and_reconnect_preserves_identity_customizations',TP),test(CONNECT,'test_reconnect_reads_later_customization_without_reissuing_grants',TW),test('tests/execution_r4/test_project_preset_update.py','test_review_advances_only_unchanged_defaults_and_finish_recovers_once',E+'pr03-preset-evolution-reconnect-installed.xml'),test(REUSE,'test_bare_connect_reuses_project_and_current_authority_without_rewrite',CB,'connector')],
    'Preservação de campos/IDs/defaults é contratual; não prova configuração efetiva dentro do provedor (T43).')
row(42,['DX-18','DX-19'],
    'Colisão de agent_id é recusada antes/depois do teste, sem adoção. Duas composições concorrentes do mesmo root criam uma vez; root diferente nunca adota. Conexões locais ambíguas exigem seleção.',
    [test(IDENT,'test_colliding_identity_is_never_adopted_or_modified',TP),test('tests/test_remote_setup_server.py','test_concurrent_same_root_creates_once_and_other_root_never_adopts',RB3),test(REUSE,'test_ambiguous_saved_connections_require_selection',CB,'connector')],
    'Concorrência canônica e escolha explícita são comprovadas com SQLite real; não requer login/inferência.')
row(43,['DX-16','DX-18'],
    'Referências, provider_home, configuração e guards são preservados/materializados no host, mas nenhum relatório demonstra o processo de harness real lançado pelo serviço usando todos os valores efetivos revisados.',
    [test(CR,'test_discovered_provider_home_is_visible_in_review_and_not_secret',CB,'connector'),test('tests/unit/test_launch_configuration.py','test_host_approved_environment_qualifies_once_after_materialization',E+'pr03-remote-preset-connector-installed.xml','connector')],
    'O callback de ambiente e fixture nativa não provam instruções/modelo/ferramentas/limites efetivos do provedor. Configuração apenas no shell não pode ser presumida.',
    [ref(CAT,locator='tasks[id=DX-18].pending')],
    pending='Campanha no processo real lançado pelo serviço, local e no host Connector aplicável, comparando instruções/modelo/ferramentas/limites revisados e configurados; registrar configuração shell-only como indisponível sem substituição silenciosa.',
    verified_subscopes=['reference_only_host_configuration','approved_provider_home_and_materialization_guards'])
row(44,['DX-18','DX-19'],
    'Flags padrão úteis e limitadas, ator/self, escopo de workspace e recusa de administração/política têm provas retidas. Root concluiu a qualificação instalada focada dos 3 casos de inbox alheia; a leitura desta evidência fecha a única lacuna específica localizada.',
     [test(IDENT,'test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key',TP),test('tests/execution_r4/test_coordination_cli.py','test_workspace_visibility_is_rejected_before_any_server_effect',E+'pr05-coordination-cli-release-installed.xml'),test('tests/test_permissions.py','test_agent_register_is_self_only_when_authenticated',E+'pr03-terminal-identity-installed.xml'),test('tests/test_operator_auth.py','test_agent_key_cannot_configure_human_account_and_still_authenticates_agent',E+'pr03-terminal-identity-installed.xml'),test(POLICY,'test_participant_cannot_initialize_server_policy',TP),test('tests/execution_r4/test_session_read_tools.py','test_another_agent_inbox_is_denied','C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/nexus-inbox-scope/canonical/tests.xml')],
    'Não requer provider/M1. A nova execução foi feita pelo root, não por esta auditoria. Teste usa HTTP MCP/capability e precondição READY sintética; não é qualificação do harness. Root curará os arquivos Temp citados no destino público.',
    [ref('src/okto_nexus/application/project_preset.py'),ref('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/nexus-inbox-scope/result.json'),ref('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/nexus-inbox-scope/canonical/campaign.json'),ref('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/nexus-inbox-scope/package-proof.json')],
    verified_subscopes=['reviewed_bounded_default_permissions','workspace_refusal','self_identity_guard','agent_cannot_administer_operator_account_or_policy'])
row(45,['DX-20'],
    'Terminal envia decisão canônica com revisão e resposta explícitas; Core valida resposta. Ator/recipient/hash/revisão/validade/grant/escopo inválidos não criam operação. Texto de prompt não substitui esse endpoint.',
    [test(WORK,'test_native_decision_response_loss_recovers_canonical_result_and_keeps_answers_out_of_profile',TW),test('tests/execution_r4/test_native_decisions.py','test_invalid_or_stale_decision_cannot_create_an_operation',E+'r3-cooperative-drain/installed/nexus-installed-v1/canonical/tests.xml'),test('tests/test_terminal_native_input.py','test_permission_has_no_default_approval',TW)],
    'VERIFIED para o contrato de decisão e autoridade, com requests sintéticas. M1 real local/remoto permanece T39/T40; não é um gate adicional deste predicado puro.')
row(46,['DX-10','DX-17','DX-20'],
    'Recuperação reconstrói a fachada dos checkpoints e recupera o mesmo operation/decision, sem segundo envio. Request/handoff usam IDs duráveis e têm morte real de CLI/retomada no mesmo contrato.',
    [test(WORK,'test_lost_submission_response_recovers_same_work_without_duplicate_dispatch',E+'r3-joint-contracts/recovery/ci/tests.xml'),test(WORK,'test_native_decision_response_loss_recovers_canonical_result_and_keeps_answers_out_of_profile',E+'r3-joint-contracts/recovery/ci/tests.xml'),test('tests/test_terminal_cooperation.py','test_crash_recovery_preserves_one_effect_and_same_ids',E+'r3-joint-contracts/recovery/ci/tests.xml'),test('tests/execution_r4/test_cooperation_cli.py','test_real_process_death_after_exchange_commit_recovers_installed_entrypoint',E+'pr04-cooperation-facade-cli-installed.xml')],
    'Work/decision são retomados por nova fachada/checkpoint; o processo real reiniciado é o CLI de coordenação. Esses alcances ficam separados, sem alegar crash de provedor ou campanha M1 real.',
    [ref(E+'r3-joint-contracts/recovery/reports.json')])
row(47,['DX-20','DX-21'],
    'Reabrir a fachada recupera operation/session canônicos e continua só enquanto a sessão permite; sair do CLI não fecha trabalho. Sessão indisponível recusa continuação e orienta --new-session explícito, sem replay/contexto fabricado.',
    [test(WORK,'test_send_result_reopen_continue_and_close_share_canonical_session',TW),test(WORK,'test_leaving_interactive_cli_does_not_interrupt_or_close_service_owned_work',TW),test(WORK,'test_profile_without_work_checkpoint_reuses_session_but_observes_only_its_own_initial_turn',TW),test(REUSE,'test_bare_connect_reuses_project_and_current_authority_without_rewrite',CB,'connector')],
    'Contrato de reopen e sessão canônica qualificado com peer sintético. Continuidade de conversa de um harness/provedor real só pode ser alegada na campanha desse caminho.',
    [function('src/okto_nexus/application/terminal_work.py','submit'),ref('docs/terminal-work.md',line=39,end_line=46)])
row(48,['DX-18','DX-21'],
    'Perfil/daemon não substituem autoridade: runtime disabled não recebe teste/grant; grant expirado/exaurido só é renovado por revisão explícita; sessão/lease antiga não migra. Política explícita desabilitada é respeitada antes de probes.',
    [test('tests/execution_r4/test_project_preset_update.py','test_disabled_runtime_stays_disabled_without_test_or_grant',PE),test(POLICY,'test_explicit_disabled_policy_is_preserved_before_probes',TP),test('tests/execution_r4/test_terminal_authorization.py','test_renewal_does_not_rebind_or_close_an_exhausted_live_session',E+'pr03-terminal-authorization-installed.xml'),test('tests/execution_r4/test_remote_renewal.py','test_remote_revocation_keeps_recovered_receipt_historical_and_participant_cannot_renew',RENEW)],
    'Regras de admissão e revogação são canônicas e não precisam de provedor real para provar recusa; não qualifica duração infinita ou replay após crash.')
row(49,['DX-12','DX-21'],
    'Browser real contra wheel instalado personaliza nome/papel do mesmo agente; identity/key/permissions/configuração/grants/histórico permanecem. Reopen terminal não reaplica defaults nem cria outro vínculo.',
    [test('tests/execution_r4/test_project_dashboard.py','test_dashboard_personalization_and_terminal_reopen_preserve_identity_history_and_grants',E+'pr03-project-dashboard-installed.xml')],
    'Browser/HTTP/SQLite reais, harness checks sintéticos; prova de continuidade dos objetos e UX, não uso efetivo de provedor.',
    [ref(E+'pr03-project-dashboard-browser.json')])
row(50,['DX-07','DX-20'],
    'O aceite não promove processo/sessão pronta a trabalho. Doctor mantém trabalho/participação UNKNOWN e relatórios mantêm M1 aberto enquanto a rota real completa não é qualificada.',
    [test(DIAG,'test_ready_connection_does_not_prove_provider_login_participation_or_work',DI),test(DIAG,'test_ready_session_open_is_not_a_productive_result',DI)],
    'VERIFIED é a regra de honestidade/recusa de aceite, não afirmação de M1. T39/T40 e configurações reais permanecem pendentes.',
    [ref(E+'pr03-terminal-work.md'),ref(CAT,locator='tasks[id=DX-20].pending')])

assert [r['id'] for r in rows]==IDS
def write(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
result=dict(format='r3.dx-remaining-scenarios',version=1,base_head='4855abd56ae4733a3e0445d835a085a697dda1df',
            ids=IDS,plan=planref,related_catalog=ref(CAT),scenarios=rows,
            status_counts=dict(Counter(r['proposed_status'] for r in rows)),
            new_tests_run=0,product_imports=False,checkout_edits=False,ledger_edits=False,
            method='Finite read of the selected literals, current source/assertions and retained installed XML/browser reports. No provider, account, OS service or campaign executed.',
            honest_real_campaign_boundary='T34/T38/T39/T40/T43 remain pending for exactly described real predicates. T44 closes after reading the 3-case installed qualification executed by root. T50 is an honesty rule and does not close M1.',
            outside_scope='No other scenario or acceptance status reviewed/promoted.')
write('matrix.json',result)
write('input-manifest.json',dict(files=sorted(inputs.values(),key=lambda x:(x['repository'],x['path']))))
nodes={(t['report']['path'],n) for r in rows for t in r['tests'] for n in t['passed_nodes']}
changed=[repo+':'+path for (repo,path),value in inputs.items() if sha((REPOS[repo]/path).read_bytes())!=value['sha256']]
assert not changed,changed
write('verification.json',dict(literal_matches=len(rows),retained_report_node_pairs=len(nodes),input_files_unchanged=len(inputs),new_tests_run=0))
summary=['# Cenários DX restantes — reconciliação finita','',
         'Escopo exato: '+', '.join(IDS)+'.','',
         'Propostas: '+json.dumps(result['status_counts'])+'. Nenhum status foi editado.','',
         'Pendências reais: T34 login ausente de provedor real; T38 instalação nova com harness/provedor efetivamente prontos; T39/T40 campanhas produtivas local/remota; T43 configuração efetiva do processo. Não se exige M1 para os demais predicados contratuais.','',
         'T44: root executou os 3 parâmetros existentes no pacote instalado; a matriz lê esse novo XML e fecha a lacuna específica. Não houve execução por esta auditoria, criação de teste ou exigência de provedor. Os paths Temp precisam ser curados pelo root.','',
         'T50 pode ser VERIFIED como honestidade de aceite. Isso preserva M1 aberto.','',
         '| ID | Proposta | Pendência literal |','|---|---|---|']
summary += ['|'+r['id']+'|'+r['proposed_status']+'|'+(r['specific_pending'] or 'Nenhuma no contrato/escopo declarado.').replace('|','\\|')+'|' for r in rows]
summary += ['',f'{len(nodes)} pares relatório/node PASS conferidos por parsing, {len(inputs)} entradas públicas citadas. Toda prova sintética, real de protocolo, browser ou processo está limitada ao seu alcance; nenhuma cadeia de provedor/M1 é fabricada por junção de componentes.']
(OUT/'summary.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
names=['matrix.json','summary.md','input-manifest.json','verification.json','reconcile.py']
write('artifact-manifest.json',dict(public_allowlist=names,files=[dict(path=n,sha256=sha((OUT/n).read_bytes()),bytes=(OUT/n).stat().st_size) for n in names],excludes=['credentials','private JSON','DB','venv','personal provider state']))
print(json.dumps(dict(path=str(OUT),counts=result['status_counts'],nodes=len(nodes),inputs=len(inputs),matrix_sha256=sha((OUT/'matrix.json').read_bytes()),manifest_sha256=sha((OUT/'artifact-manifest.json').read_bytes())),indent=2))
