"""Finite read-only DX scenario reconciliation. Does not import product or run tests."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).parent
REPOS = {'nexus': ROOT, 'core': ROOT.parent/'okto-nexus-connector-core', 'connector': ROOT.parent/'okto-nexus-connector'}
HEAD = '4855abd56ae4733a3e0445d835a085a697dda1df'
E = 'plans/agent_ops/evidence/'
CATALOG = E+'r3-task-reconciliation/dx/matrix.json'
PLAN = 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
IDS = [f'DX-T{i:02}' for i in range(1,15)]+['DX-T26','DX-T28']
inputs = {}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def ref(path, repository='nexus', **details):
    repository = repository.lower()
    raw = (REPOS[repository]/path).read_bytes()
    item = dict(repository=repository, path=path, sha256=sha(raw), bytes=len(raw))
    inputs[(repository,path)] = item
    return item | details

def read(path, repository='nexus'):
    ref(path,repository)
    return json.loads((REPOS[repository]/path).read_text(encoding='utf-8'))

catalog = {t['id']:t for t in read(CATALOG)['tasks']}
ledger = read('plans/agent_ops/ledger.json')
plan_ref = ref(PLAN)
literals = {}
for line,text in enumerate((ROOT/PLAN).read_text(encoding='utf-8').splitlines(),1):
    m = re.match(r'^\|\s*(DX-T\d{2})\s*\|\s*(.*?)\s*\|$',text)
    if m and m[1] in IDS:
        literals[m[1]] = (line,m[2])
assert set(literals)==set(IDS)

def function(path, name, repository='nexus'):
    raw = (REPOS[repository]/path).read_text(encoding='utf-8')
    nodes = [n for n in ast.walk(ast.parse(raw)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    assert len(nodes)==1,(path,name,len(nodes))
    n = nodes[0]
    return ref(path,repository,symbol=name,line=n.lineno,end_line=n.end_lineno,
               function_sha256=sha(ast.get_source_segment(raw,n).encode('utf-8')),
               assertions=[dict(line=x.lineno,expression=ast.unparse(x.test)) for x in ast.walk(n) if isinstance(x,ast.Assert)],
               exception_oracles=[dict(line=x.context_expr.lineno,expression=ast.unparse(x.context_expr)) for x in ast.walk(n) if isinstance(x,ast.withitem) and isinstance(x.context_expr,ast.Call) and ast.unparse(x.context_expr.func).endswith('.raises')])

def test(path, name, report, repository='nexus'):
    source = function(path,name,repository)
    classname = path[:-3].replace('/','.')
    parsed = ET.parse(ROOT/report)
    matches = [x for x in parsed.findall('.//testcase') if x.get('classname')==classname and (x.get('name')==name or x.get('name','').startswith(name+'['))]
    assert matches,(report,classname,name)
    assert all(not any(x.find(k) is not None for k in ('failure','error','skipped')) for x in matches),(report,name)
    historical = [t for task in catalog.values() for t in task['tests'] if t['path']==path and t['symbol']==name and t['repository'].lower()==repository]
    if historical:
        source['retained_catalog_sha256']=historical[0]['sha256']
        source['same_file_bytes_as_retained_catalog']=source['sha256']==historical[0]['sha256']
    return dict(source=source, report=ref(report), nodes=[dict(node_id=x.get('classname')+'::'+x.get('name'),status='PASS') for x in matches],
                reading='Existing installed XML only; no new test execution; no sum with overlapping campaigns.')

def sources(tasks):
    result={}
    for ident in tasks:
        for s in catalog[ident]['sources']:
            r=ref(s['path'],s['repository'],symbol=s.get('symbol'),retained_line=s.get('line'),
                  retained_catalog_sha256=s['sha256'])
            r['same_file_bytes_as_retained_catalog']=r['sha256']==s['sha256']
            result[(r['repository'],r['path'],r['symbol'])]=r
    return list(result.values())

P='tests/execution_r4/test_participant_init.py'
D='tests/execution_r4/test_participant_doctor.py'
L='tests/execution_r4/test_participant_launch.py'
C='tests/test_participant_config.py'
F='tests/test_config_persistence.py'
G='tests/execution_r4/test_project_diagnostics.py'
CP=E+'pr04-participant-init-core-installed.xml'
NP=E+'pr04-participant-removal-installed.xml'
DP=E+'pr03-project-doctor-installed.xml'
RP=E+'pr03-preset-evolution-installed.xml'
CO=E+'pr04-cooperation-facade-cli-installed.xml'
rows=[]

def row(num, tasks, rationale, tests, limit, extra=(), pending=None):
    ident=f'DX-T{num:02}'
    line,literal=literals[ident]
    old=ledger['scenarios'][ident]
    assert literal==old['requirement'],ident
    row=dict(id=ident,literal_requirement=literal,plan_line=line,ledger_status_read=old['status'],
             proposed_status='VERIFIED' if pending is None else 'IN_PROGRESS',
             recommendation_scope='Windows/current implemented contract and explicitly retained campaign scopes',
             rationale=rationale,related_tasks=tasks,
             implementation=sources(tasks),tests=tests,evidence=list(extra),
             limit=limit,specific_pending_for_literal=pending,
             stale_status_explanation='O texto histórico mistura este cenário com cliente/provedor/cofre/M1 mais amplos; esses gates não substituem o predicado literal aqui revisado.',
             prior_verified_subscopes=old.get('subscopes',{}))
    rows.append(row)

common='Evidência instalada histórica reaproveitada por seus nodes e assertions; leitura atual não é reexecução do wheel atual. Windows/local; identidades, arquivos, vaults e pares nativos sintéticos quando declarado.'
chain='Não qualifica a cadeia completa OS vault→launcher distribuído→cliente real→cooperação canônica. As provas de componentes e initialize com variável manual continuam distintas; essa campanha não foi executada aqui.'

row(1,['DX-05','DX-19'],
    'Init lê a identidade do Bearer e exige seleção existente; não há caminho de criação/rotação. Reconnect conserva setup/entrada/runtime e o guia seleciona identidade sem mutá-la.',
    [test(P,'test_review_apply_reconnect_preserves_runtime_and_other_configuration',NP),test(P,'test_workspace_and_identity_mismatch_refused_without_local_effect',NP)],
    common+' O snapshot deste teste cobre configuração/grants/bindings; a ausência de criação/rotação é também explícita no use case read-only, não inferida desse snapshot parcial.',
    [function('src/okto_nexus/application/participant_setup.py','participant_context'),ref(E+'pr04-participant-guide/browser/browser-report.json',locator='checks[name=existing_identity_readonly]')])
row(2,['DX-05','DX-19'],
    'Preparação participante exige identidade atual e não concede autoridade. Actor participante/revogado é recusado no bootstrap; snapshot canônico permanece idêntico.',
    [test(P,'test_participant_context_uses_bearer_identity_without_self_elevation',NP),test('tests/test_remote_setup_server.py','test_participant_and_revoked_principal_cannot_read_or_bootstrap',E+'pr03-remote-bootstrap/candidate-v3/nexus/installed.xml')],common,
    [function('src/okto_nexus/application/participant_setup.py','participant_context')])
row(3,['DX-05','DX-13'],
    'O fixture já possui um binding managed antes de adicionar a entrada participante. Apply/reconnect deixam bindings, grants, execution policy e runtime overrides idênticos.',
    [test(P,'test_review_apply_reconnect_preserves_runtime_and_other_configuration',NP)],common,
    [function('tests/execution_r4/test_connection_setup_recovery.py','snapshot'),function(P,'setup')])
row(4,['DX-01','DX-03','DX-05'],
    'Plan deixa arquivo/vault intactos; apply usa entrada revisada e ownership, preservando outras entradas. Aprovação/hash ou configuração alterados são recusados antes dos efeitos.',
    [test(C,'test_reference_only_round_trip_and_selected_entry_ownership',CP,'core'),test(P,'test_review_drift_blocks_before_vault_or_file_effect',NP)],common)
row(5,['DX-03','DX-05'],
    'CAS do documento rejeita plan stale; edição externa durante apply também é detectada antes do replace e seus bytes são preservados.',
    [test(F,'test_noncooperating_edit_during_apply_detected_before_replace',CP,'core'),test(F,'test_conflicting_edit_never_replaced_or_backed_up',CP,'core'),test(C,'test_changed_owned_entry_and_stale_review_are_refused',CP,'core')],common)
row(6,['DX-01','DX-03'],
    'JSON/TOML preservam outros MCPs, modelo personalizado e posterior edição alheia; backup mantém bytes originais e remoção alcança só a entrada possuída.',
    [test(C,'test_reference_only_round_trip_and_selected_entry_ownership',CP,'core'),test(F,'test_create_and_update_preserve_source_backup_and_other_entries',CP,'core')],common)
row(7,['DX-01','DX-02','DX-03'],
    'Round-trip parametrizado Claude JSON/Codex TOML cobre caminho com espaços/Unicode, conteúdo Unicode e CRLF; JSON/TOML inválidos, chaves duplicadas, forma errada e UTF-8 inválido falham fechados.',
    [test(C,'test_reference_only_round_trip_and_selected_entry_ownership',CP,'core'),test(C,'test_invalid_or_duplicate_documents_fail_without_rewriting',CP,'core')],
    common+' Contrato do editor suportado; não exige executar modelo nem cliente para provar parsing/preservação.')
row(8,['DX-03','DX-06'],
    'Falha antes dos bytes de backup/replacement preserva o original; falha após replace mantém substituto íntegro e OUTCOME_UNKNOWN/possible_effect. Checkpoint perdido retoma por inspeção do mesmo efeito.',
    [test(F,'test_host_protection_runs_before_sensitive_bytes_and_failure_preserves_source',CP,'core'),test(F,'test_post_replace_sync_failure_reports_possible_effect',CP,'core'),test(P,'test_lost_checkpoint_resumes_same_intent_by_observing_effect',NP),test(P,'test_uncertain_file_with_later_edit_is_preserved_without_new_intent',NP)],
    common+' Fault injection nos limites de escrita/backup/replace e perda de checkpoint; não declara teste de queda de energia física. O literal não exige esse novo tipo de campanha.')
row(9,['DX-01','DX-04','DX-05'],
    'Config/exportação carrega referência de ambiente, não valor. CLI não recai em entrada com eco; erros HTTP/processo são sanitizados; processo filho recebe variável escopada, sem mutar pai. Guia/browser gera apenas comandos públicos.',
    [test('tests/test_harness_config.py','test_direct_http_config_has_no_proxy_or_secret',CP,'core'),test(P,'test_review_apply_reconnect_preserves_runtime_and_other_configuration',NP),test(P,'test_cli_never_falls_back_to_echoing_key',NP),test(P,'test_malformed_http_errors_never_echo_response_or_key',NP),test(L,'test_cli_does_not_echo_process_errors_or_secrets',NP),test(L,'test_real_subprocess_receives_reference_without_parent_mutation',NP)],
    common+' '+chain+' Ausência de segredo refere-se às superfícies e homes de campanha explicitamente inspecionados, não à história Git nem a todos os plugins/clientes possíveis.',
    [ref(E+'pr04-participant-guide/browser/browser-report.json'),ref(E+'pr04-participant-guide/reports.json'),ref(E+'pr04-participant-launch-native.json',locator='cases[*].argv/secret_files/inference_requested'),ref(E+'r3-public-artifact-review/verification.json')])
row(10,['DX-02','DX-04','DX-07'],
    'Variável ausente/inválida produz FAIL no diagnóstico de ambiente; existência só prova o processo doctor e mantém client_reload/MCP UNKNOWN. Campanha com clientes reais registra ausência sem initialize autenticado, nunca como sucesso.',
    [test(D,'test_environment_check_proves_only_current_doctor_context',NP)],
    common+' '+chain+' Claude 2.1.317 ficou pending e Codex 0.166.0 registrou tools_error_present quando ausente; não se inventa mensagem diagnóstica Claude que o relatório não capturou. O diagnóstico explícito Nexus é qualificado pelo teste de contexto.',
    [ref(E+'pr04-participant-launch-native.json',locator='cases[credential_available=false]'),ref('plans/agent_ops/campaigns/participant-environment.py',locator='child_environment + direct fixture process launch; not OS vault')])
row(11,['DX-04','DX-05'],
    'HTTP recusa redirect antes de seguir Location; somente a requisição inicial autorizada chega ao servidor. Alteração de contexto/configuração da origem falha antes de spawn.',
    [test(P,'test_actual_http_redirect_does_not_forward_bearer',NP),test(L,'test_drift_refuses_before_process_effect',NP),test(C,'test_changed_owned_entry_and_stale_review_are_refused',CP,'core')],
    common+' Teste TCP real de redirect e guards de contexto; não é campanha TLS/hosts físicos nem todas as políticas de redirect de clientes externos.',
    [ref(E+'pr04-participant-guide/browser/browser-report.json',locator='checks[name=codex_https_port_preserved or remote_http_refused]')])
row(12,['DX-07'],
    'Doctor padrão usa só metadados e recibos históricos: guards fazem falhar qualquer vault/HTTP/processo/recovery; arquivos e tabelas ficam idênticos. Modos ativos continuam flags explícitas.',
    [test(D,'test_passive_doctor_preserves_files_without_vault_http_process_or_recovery',NP),test('tests/execution_r4/test_cooperation_cli.py','test_doctor_reads_historical_proof_without_live_claims_credentials_or_effects',CO)],common)
row(13,['DX-07'],
    'MCP real TCP initialize/list_tools autenticado deixa tools_called=0 e participação/handoff/work UNKNOWN, sem abrir heartbeat de sessão agente ou alterar tabelas canônicas.',
    [test(D,'test_actual_tcp_mcp_is_not_agent_participation_or_model_work',NP)],
    common+' É a fronteira de prova, não qualificação de cooperação de clientes reais.')
row(14,['DX-07','DX-08'],
    'Sucesso técnico de setup não é cooperação. Mesmo texto NEXUS_CONNECTION_OK em reply legado/parent errado deixa participação UNKNOWN; prova exige recibo/proveniência e correlação canônica, não texto do modelo.',
    [test('tests/execution_r4/test_cooperation_cli.py','test_text_or_unrelated_reply_cannot_qualify_exchange',CO),test(G,'test_current_open_eligibility_does_not_run_another_probe_or_turn',DP),test('tests/test_cooperation_reply_read.py','test_native_canonical_publication_reports_outcome_without_model_text_proof',E+'pr04-cooperation-behavior-installed.xml')],
    common+' Teste de conexão/probe nativo sintético e Core real com peer sintético; nenhum resultado é promovido a cooperação real de harnesses.',
    [function('tests/execution_r4/test_cooperation_cli.py','reply')])
row(26,['DX-06','DX-13','DX-21'],
    'Finish managed continua atômico/idempotente. Falha tardia reverte identidade/chave/configuração; mudança concorrente de preset, identidade, grant ou endpoint retorna CONFLICT e conserva snapshot de grants/bindings/receipts.',
    [test('tests/execution_r4/test_connection_setup.py','test_finish_atomic_idempotent',RP),test('tests/execution_r4/test_terminal_identity.py','test_late_finish_failure_rolls_back_identity_key_and_every_setup_object',RP),test('tests/execution_r4/test_project_preset_update.py','test_concurrent_change_refuses_finish_without_repair_or_authority',RP)],common,
    [function('tests/execution_r4/test_connection_setup_recovery.py','snapshot')])
row(28,['DX-05','DX-07','DX-11'],
    'JSON e exits são oráculos diretos: init/connect compartilham saída/checkpoints, doctor mantém shape/exits e usage/interrupt têm códigos separados. Invocações instaladas fora checkout confirmam JSON de falha sem efeitos.',
    [test(P,'test_init_and_connect_participant_share_review_and_cli_checkpoints',NP),test('tests/test_doctor_diagnostic_format.py','test_managed_legacy_shape_and_exit_are_unchanged',E+'pr10-correlation/installed/diagnostics/installed.xml'),test('tests/test_doctor_diagnostic_format.py','test_bad_selector_is_usage_error_before_any_effect',E+'pr10-correlation/installed/diagnostics/installed.xml'),test('tests/test_doctor_diagnostic_format.py','test_interrupt_exit_is_unchanged',E+'pr10-correlation/installed/diagnostics/installed.xml')],
    common+' Contrato de saída não exige inferência produtiva nem prova de cliente/cofre.',
    [ref(E+'pr04-participant-removal-cli.json'),ref(E+'pr03-project-doctor-cli.json')])

assert [r['id'] for r in rows]==IDS
assert all(r['specific_pending_for_literal'] is None for r in rows)
nodes={(t['report']['path'], n['node_id']) for r in rows for t in r['tests'] for n in t['nodes']}
changed_sources=sorted({s['repository']+':'+s['path'] for r in rows for s in r['implementation'] if not s['same_file_bytes_as_retained_catalog']})

def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

result=dict(format='r3.dx-scenario-reconciliation',version=1,base_head=HEAD,plan=plan_ref,ids=IDS,
    method='Finite source/assertion and retained installed XML/JSON/browser evidence read. No product imports, test/campaign execution, checkout/ledger mutation, credential or personal state access.',
    related_task_catalog=ref(CATALOG),scenario_count=len(rows),status_counts=dict(Counter(r['proposed_status'] for r in rows)),
    scenarios=rows,distinct_retained_report_node_pairs=len(nodes),
    changed_product_files_vs_historical_catalog=changed_sources,
    scope_limit=common,credential_chain_limit=chain,
    outside_scope='Only the listed sixteen scenarios were reviewed; no other scenario/task/acceptance status is proposed or changed.',
    no_runtime_claim='All PASS labels belong to retained artifacts. Reading XML is not a new qualification run.',
    global_acceptance='No M1/M2/full R3 promotion; real provider/client/vault/native-service campaigns remain separate.')
write('matrix.json',result)
write('input-manifest.json',dict(files=sorted(inputs.values(),key=lambda x:(x['repository'],x['path'])),selection='explicit cited public files only'))
summary=['# Reconciliação finita de cenários DX','',
    'Base Nexus: `'+HEAD+'`. Escopo exato: DX-T01…14, DX-T26 e DX-T28.', '',
    '**Recomendação: 16 VERIFIED**, no escopo literal documentado. Nenhuma pendência concreta desses 16 predicados foi localizada. Nenhum status foi editado.', '',
    'Os IN_PROGRESS carregam limites de campanhas mais amplas. A prova de init, edição transacional, CAS, proteção de credenciais nas superfícies selecionadas e honestidade dos diagnósticos não exige executar um provedor.', '',
    'DX-T10: diagnóstico de ambiente FAIL/UNKNOWN é explícito e restrito ao contexto observado. A campanha real com variável ausente registrou Claude pending e Codex tools_error_present; não se inventa um diagnóstico textual Claude. Ela não passou por cofre real e não demonstra a cadeia completa cofre→launcher→cliente→cooperação.', '',
    'DX-T08: interrupções são fault injection antes de escrita/backup/replacement e após replace, além de perda de checkpoint; não são queda de energia física.', '',
    'DX-T09: a ausência de segredo é comprovada nas superfícies/arquivos/browser e homes explicitamente examinados; não declara cobertura de toda história Git nem de plugins arbitrários.', '',
    '| ID | Razão específica |','|---|---|']
summary += ['|'+r['id']+'|'+r['rationale'].replace('|','\\|')+'|' for r in rows]
summary += ['',f'{len(nodes)} pares relatório/node PASS foram conferidos por parsing dos XMLs retidos. Nenhum teste novo, conta, serviço nativo ou inferência foi executado.', '',
    'Cada entrada da matriz inclui literal/linha do plano, implementação com SHA, teste com assertions e oráculos de erro, node PASS/XML com SHA, limite e pendência específica (null). M1/M2/R3 e campanhas fora desse escopo permanecem abertos.']
(OUT/'summary.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
changed_inputs=[repository+':'+path for (repository,path),item in inputs.items()
                if sha((REPOS[repository]/path).read_bytes())!=item['sha256']]
assert not changed_inputs,changed_inputs
write('verification.json',dict(exact_requested_scenarios=len(rows),literal_plan_ledger_matches=len(rows),
      retained_report_node_pairs_passed=len(nodes),input_files_unchanged=len(inputs),
      implementation_bytes_match_retained_catalog=not changed_sources,new_tests_run=0,
      product_or_ledger_edits=False,all_artifacts_written_only_under=str(OUT)))
names=['matrix.json','summary.md','input-manifest.json','verification.json','reconcile.py']
write('artifact-manifest.json',dict(public_allowlist=names,files=[dict(path=n,sha256=sha((OUT/n).read_bytes()),bytes=(OUT/n).stat().st_size) for n in names],excludes=['private JSON','DB','credentials','venv','personal client state']))
print(json.dumps(dict(output=str(OUT),ids=len(rows),status_counts=result['status_counts'],retained_report_node_pairs=len(nodes),input_files=len(inputs),changed_catalog_sources=changed_sources,
                     matrix_sha256=sha((OUT/'matrix.json').read_bytes()),manifest_sha256=sha((OUT/'artifact-manifest.json').read_bytes())),indent=2))
