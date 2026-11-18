"""Read-only evidence reconciliation; never changes the execution ledger."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PACKAGE = Path('C:/Users/jpamb/Downloads/NEXUS_HOME_ESTADOS_R1_PACOTE_CODEX')
ledger_path = PACKAGE / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger_bytes = ledger_path.read_bytes()
ledger = json.loads(ledger_bytes)
proof_path = HERE / 'delivery-implementation/final/qualification.json'
proof = json.loads(proof_path.read_text(encoding='utf-8'))
nodes = proof['cuts']['metadata-final']['nodes']
assert len(nodes) == 58 and all(node['status'] == 'PASS' for node in nodes)


def match(*fragments):
    result = [node for node in nodes if any(fragment in node['name'] for fragment in fragments)]
    assert result, fragments
    return result


coverage = {}


def add(identifier, fragments, assertions, missing, layers):
    coverage['HST-T-' + identifier] = dict(executed_assertions=assertions,
        executed_tests=match(*fragments), executed_layers=layers, missing=missing)


presentation_gap = 'Apresentação integrada/validador e navegador no corte final; fixtures/Node não equivalem a browser.'
sql_gap = 'Caso correspondente no SQLite/HTTP do novo contrato, além da função pura.'
add('E01', ['test_turn_outcome_does_not_invent', 'test_standalone_sql_null'],
    ['SUCCEEDED sem handoff é turno; tarefa/verificação não aplicáveis e historical=false; campo legado preservado.'],
    [presentation_gap], ['unit', 'sqlite_read_fixture'])
add('E02', ['test_task_status_is_independent_and_completed_never_proves_approved[CLAIMED'],
    ['Resultado produtivo succeeded não muda task_state claimed nem cria approved.'], [sql_gap, presentation_gap], ['unit'])
add('E03', ['test_pending_and_positive_proof_keep_one_result_id'],
    ['Entrega não nativa VERIFYING aparece somente na apresentação2; verification pending, ID preservado ao concluir.'],
    ['Ocorrência/badge de verificação e colocação do harness exigem integração separada.', presentation_gap], ['canonical_application_sqlite'])
add('E04', ['test_task_status_is_independent_and_completed_never_proves_approved[COMPLETED', 'test_completed_without_verification_contract'],
    ['COMPLETED sem proof e com critérios conhecidos não é approved; sem contrato de verificação é not_applicable e sem evidence_ref.'],
    ['Artefato histórico real/recibo antigo em instalação isolada, além da função pura e serviço atual.', presentation_gap], ['unit', 'canonical_application_sqlite'])
add('E05', ['test_exact_verification_proof_has_opaque_reference[pass', 'test_pending_and_positive_proof_keep_one_result_id'],
    ['Pass autorizado do claim/revisão exatos produz approved e evidence_ref do evento; uma entrega lógica, GET sem writes.'],
    [presentation_gap, 'Caminho HTTP autenticado versão2 em pacote instalado.'], ['unit', 'canonical_application_sqlite'])
add('E06', ['test_proof_of_another_claim', 'test_rejected_delivery_uses_old_epoch', 'test_historical_claim_is_explicit'],
    ['Outro claim/workspace/handoff/revisão/ator/ordem causal não é herdado; retrabalho cria entrega atual distinta, histórico preservado.'],
    [presentation_gap], ['unit', 'canonical_application_sqlite'])
add('E07', ['test_exact_verification_proof_has_opaque_reference[fail', 'test_rejected_delivery_uses_old_epoch'],
    ['Fail referencia epoch anterior ao incremento; delivery rejected, tarefa claimed; não vira cancelamento ou approved na versão nova.'],
    [presentation_gap], ['unit', 'canonical_application_sqlite'])
add('E08', ['test_turn_outcome_does_not_invent_task_or_verification[FAILED'],
    ['FAILED gera execution_outcome failed independente de tarefa/verificação.'],
    [sql_gap, 'Saída parcial/artefatos e ausência de retry na UI.', presentation_gap], ['unit'])
add('E09', ['test_turn_outcome_does_not_invent_task_or_verification[CANCELLED'],
    ['CANCELLED gera execution_outcome cancelled, sem reinterpretar tarefa.'],
    [sql_gap, 'Saída parcial/artefatos preservados na UI.', presentation_gap], ['unit'])
add('E10', ['test_task_status_is_independent_and_completed_never_proves_approved[REJECTED'],
    ['Task_state rejected permanece separado de execution_outcome.'],
    ['Handoff REJECTED sem resultado nativo no SQLite/HTTP e mensagem da apresentação.', presentation_gap], ['unit'])
add('E11', ['test_cleanup_and_content_do_not_overwrite', 'test_standalone_sql_null', 'test_overview_real_fixture_is_read_only'],
    ['SUCCEEDED continua succeeded com cleanup pending; RELEASED/REQUESTED/ausência separados; SQL fixture conserva cleanup pendente.'],
    ['Não é prova de cleanup real de processo ou contenção nativa.', presentation_gap], ['unit', 'sqlite_read_fixture'])
add('E12', ['test_cleanup_and_content_do_not_overwrite'],
    ['Terminal sem captura é pending; captura terminal com texto vazio não é falsamente ausente.'],
    [sql_gap, presentation_gap], ['unit'])
add('E13', ['test_external_report_has_no_native_success'],
    ['Reporte externo é evidence reported, execution/verification unknown e sem mutação do objeto de origem.'],
    ['Produtor OBS/Attention real e DeliveryDTO do quadro em SQLite/HTTP.', presentation_gap], ['unit'])
add('E16', ['test_http_result_collects_same_claim_files', 'test_http_artifact_group_uses_authorized', 'test_result_preview_seen_and_bounded', 'test_result_artifact_reference', 'test_pending_and_positive_proof_keep_one_result_id'],
    ['Artefatos por vínculos/claim/workspace antes de rank; metadata sem paths; visto canônico e ID estável na mudança de verificação.'],
    ['Itens invisíveis e inbox watermark em browser adversarial completo.', presentation_gap], ['canonical_application_sqlite', 'sqlite_http_read_fixture'])
add('A05', ['test_http_artifact_group_uses_authorized_terminal_relation_with_history_and_other_executor'],
    ['Associação de artefatos/resultados preserva executor e histórico autorizado; não agrupa por operation_id isolado.'],
    ['Quadro v2/cards e abertura contextual de operações homônimas completos.'], ['sqlite_http_read_fixture'])
add('A07', ['test_newest_foreign_workspace_operation'],
    ['Operação mais recente de workspace estrangeiro não substitui o resultado/handoff legítimo.'],
    ['Resposta atrasada de UI após troca de escopo, no browser.'], ['sqlite_http_read_fixture'])
add('D03', ['test_verification_authority_and_old_claim', 'test_pending_and_positive_proof_keep_one_result_id'],
    ['Verificação canônica existente mantém autoridade/claim; self-verifier/ator inelegível/claim antigo não escrevem proof.'],
    ['Ocorrência verification_pending destinada ao operador, badge/ação e ausência de bloqueio inferido.', 'HTTP/browser com principal humano autenticado.'], ['canonical_application_sqlite'])
add('H01', ['test_pending_and_positive_proof_keep_one_result_id', 'test_overview_real_fixture_is_read_only', 'test_each_page_uses_one_read_uow'],
    ['GET de Results não altera total_changes; uma instrução SQL por leitura e UoW existente; overview preserva contagens.'],
    ['Todas as rotas v2/expansões e controles de browser adversarial; auth telemetry separada.'], ['canonical_application_sqlite', 'sqlite_read_fixture'])
add('H02', ['test_exact_target_server_workspace_and_session', 'test_operator_authority_not_an_agent_name', 'test_newest_foreign_workspace_operation'],
    ['Referências exatas de alvo e fronteira Server/workspace/sessão; nome de agente não concede autoridade.'],
    ['Nova apresentação e erros de principal autenticado em browser.'], ['sqlite_read_fixture', 'sqlite_http_read_fixture'])
add('H03', ['test_result_artifact_reference_uses_exact_durable_operation_without_paths', 'test_business_feed_uses_real_events_not_unread_or_private_payload', 'test_external_report_has_no_native_success'],
    ['Metadata não publica path de artefato/conteúdo privado do feed; helper não projeta campo private.'],
    ['Labels hostis/HTML/ANSI/credenciais em todos novos badges, HTTP DTO e browser adversarial.'], ['unit', 'sqlite_read_fixture'])
add('H04', ['test_verification_authority_and_old_claim'],
    ['Executor não verifica própria entrega; outro ator sem elegibilidade e claim obsoleto não emitem prova nem mudam linha.'],
    ['Isso não é prova de autenticação HTTP nem de destinatário de pergunta nativa; falta o fluxo humano/browser.'], ['canonical_application_sqlite'])
add('H06', ['test_overview_real_fixture_is_read_only', 'test_same_claim_is_immutable'],
    ['Leitura não executa; novo complete no mesmo claim VERIFYING é recusado; no hash de conteúdo em GET.'],
    ['Unknown/possible_effect e CTA de recuperação no browser, sem replay.'], ['canonical_application_sqlite', 'sqlite_read_fixture'])
add('H08', ['test_external_report_has_no_native_success'],
    ['Helper de reporte não transforma seu outcome em sucesso nativo nem altera a entrada.'],
    ['Snapshot stateful de slot/claim/grant antes/depois do produtor OBS real e quadro.'], ['unit'])
add('J01', ['test_http_result_collects_same_claim_files', 'test_pending_and_positive_proof_keep_one_result_id'],
    ['Uma entrega lógica com vários artefatos e mudança de verificação mantém ID e não duplica a linha.'],
    ['Resumo integrado com 2 harnesses/3 ações/entregas compartilhadas e benchmark.'], ['canonical_application_sqlite', 'sqlite_http_read_fixture'])
add('J03', ['test_pending_and_positive_proof_keep_one_result_id', 'test_rejected_delivery_uses_old_epoch'],
    ['Cada leitura de Results instrumentada executa uma única instrução SQL, sem consulta Python por resultado.'],
    ['Medição escalonada 1/10/100, tempo/plano SQL, payload e baseline comparável; uma query não prova ausência de custo quadrático interno.'], ['canonical_application_sqlite'])
add('K02', ['test_standalone_sql_null', 'test_pending_and_positive_proof_keep_one_result_id', 'test_completed_without_verification_contract'],
    ['Campos legados de outcome/verification e ID são preservados; v1 não recebe membership VERIFYING; old contract sem proof não vira approved.'],
    ['Wheels antigo/novo e snapshot de receipts/hashes/grants em instalação isolada.'], ['canonical_application_sqlite', 'sqlite_read_fixture'])

defaults = {
    'A': 'Integração de identidade/escopo no novo quadro e HTTP; esta revisão Results não a executou por completo.',
    'B': 'Estado operacional/conectividade requer prova própria do runtime e cobertura; não inferir de Results.',
    'C': 'Agregação de bloqueio/paralelismo pertence ao backend operacional e precisa integração própria.',
    'D': 'Badge, ação e aplicação/retomada causal exigem testes próprios; decisão registrada não é aplicação nativa.',
    'E': 'Negativo específico ainda não executado neste corte; ausência no predicado SQL foi apenas inspecionada.',
    'F': 'Há relatórios Node candidatos; precisam integração pelo Root e browser real no corte final.',
    'G': 'Há componentes/controller Node candidatos; falta integração e browser real, sem escolha latest.',
    'H': 'Segurança integral do novo fluxo precisa HTTP/SQLite e browser adversarial próprios.',
    'I': 'Browser/AT não executados nesta frente; SSR/Node não comprovam foco, anúncio, zoom ou leitor real.',
    'J': 'Benchmark/contagens/expiração no dataset final ainda pendentes; testes focais não são p95/SLO.',
    'K': 'Pacote instalado, compatibilidade e rollback futuros dependem de SOURCE_READY e qualificação própria.',
    'L': 'Bloqueado: nenhuma nova autorização de provedor/harness real para Home States; não reutilizar consentimentos antigos.'}
matrix = []
for scenario in ledger['tests']:
    item = dict(scenario_id=scenario['id'], title=scenario['title'], group=scenario['group'],
        required_level=scenario['level'], ledger_template_status=scenario['status'],
        review_status='BLOCKED_NO_NEW_PROVIDER_AUTHORIZATION' if scenario['group'] == 'L' else 'NOT_RUN_IN_THIS_REVIEW',
        executed_assertions=[], executed_tests=[], executed_layers=[], missing=[defaults[scenario['group']]])
    if scenario['id'] in coverage:
        item.update(coverage[scenario['id']], review_status='PARTIAL_ASSERTIONS_EXECUTED')
    if scenario['group'] == 'L':
        item['missing'].append('Humano somente após implementação, automação e nova decisão específica; campanhas anteriores UNKNOWN permanecem bloqueios separados.')
    matrix.append(item)
assert len(matrix) == 116 and len({row['scenario_id'] for row in matrix}) == 116

external = []
for relative in ['hst00-contracts/qualification.json', 'hst04-context/qualification.json', 'hst04-controller/qualification.json', 'frontend-reproduction/qualification.json']:
    path = HERE / relative
    value = json.loads(path.read_text(encoding='utf-8'))
    external.append(dict(path=str(path.relative_to(REPO)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        status=value.get('status'), declared_node_pass=value.get('node_pass'),
        integration_status='CANDIDATE_FOR_ROOT_RECONCILIATION_NOT_PROMOTED_BY_THIS_REVIEW',
        note='Counts overlap between reports; do not sum 67+73 or promote Node to browser. The reproduction report is expected red.'))

tasks = []
for task in ledger['tasks']:
    if task['id'] not in {'HST-011', 'HST-012', 'HST-013'}:
        continue
    tasks.append(dict(task_id=task['id'], title=task['title'], implementation='SOURCE_SCOPED_IMPLEMENTED',
        qualification='PARTIAL_NOT_FULL_TASK_VERIFIED', final_source_tests=58,
        scenario_review=[row['scenario_id'] for row in matrix if row['scenario_id'] in task['tests'] and row['executed_tests']],
        remaining=[row['scenario_id'] for row in matrix if row['scenario_id'] in task['tests'] and not row['executed_tests']],
        note='Even listed assertion coverage is partial until required layers are demonstrated.'))
report = dict(at=datetime.now(timezone.utc).isoformat(), scope='READ_ONLY_RECONCILIATION_NOT_LEDGER_UPDATE',
    ledger_template_sha256=hashlib.sha256(ledger_bytes).hexdigest(), scenario_count=116,
    evidence_path=str(proof_path.relative_to(REPO)), evidence_sha256=hashlib.sha256(proof_path.read_bytes()).hexdigest(),
    final_tests=58, status_counts=dict(Counter(row['review_status'] for row in matrix)),
    tasks=tasks, scenarios=matrix, external_candidates=external,
    critical_gaps=['Causal application/resume: HTTP decision recorded, stale RUNNING or task verification cannot establish native application. D06-D12 need exact epoch/operation and causal watermark/receipt proof.',
        'L01-L04 require new explicit authorization and per-adapter evidence. Paid UNKNOWN predecessors do not authorize replay or fallback.',
        'Human acceptance comes after implementation and automated browser/installed checks; no AT or user result is inferred.',
        'No HST scenario is promoted to full PASS by this review; missing required layers remain visible.'])
(HERE / 'scenario-coverage-review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['# Revisão de cobertura HOME-STATES-R1', '',
    'Matriz somente leitura dos 116 cenários. Nenhum ledger foi alterado e nenhum teste foi executado para produzir esta revisão.', '',
    'Os 58 casos do corte Results são evidência SOURCE_ONLY: helper puro, serviço canônico e SQLite/HTTP de fixture. Não qualificam um harness real, browser, AT ou pacote final.', '',
    '## Gates que permanecem abertos', '']
lines += ['- ' + value for value in report['critical_gaps']]
lines += ['', '## HST-011–013', '', '| Tarefa | Implementação | Qualificação |', '|---|---|---|']
lines += [f"| {task['task_id']} — {task['title']} | Fonte implementada, corte 58 PASS | Parcial; não VERIFIED integral |" for task in tasks]
lines += ['', '## Matriz literal', '', '| Cenário | Resultado desta revisão | Assertions executadas / lacunas |', '|---|---|---|']
for row in matrix:
    brief = '; '.join(row['executed_assertions']) if row['executed_assertions'] else 'Sem assertion promovida nesta revisão.'
    missing = ' / '.join(row['missing'])
    lines.append(f"| {row['scenario_id']} — {row['title']} | {row['review_status']} | {brief} **Falta:** {missing} |")
lines += ['', '## Evidência de outras faixas', '',
    'Os relatórios hst00-contracts, hst04-context (73 Node), hst04-controller (67 Node antecedente) e frontend-reproduction foram apenas inventariados como candidatos para o Root. Não somar cortes sobrepostos; a reprodução esperada vermelha não é aceite. O Root integra a faixa SSR/contratos e o backend operacional separadamente.', '',
    'O JSON inclui os nomes exatos dos testes executados, as camadas, hashes e lacunas por cenário. A matriz não substitui o ledger e não declara o plano finalizado.', '']
(HERE / 'scenario-coverage-review.md').write_text('\n'.join(lines), encoding='utf-8')
assert ledger_path.read_bytes() == ledger_bytes
print(json.dumps(dict(scenarios=116, status_counts=report['status_counts'], mapped_assertion_scenarios=len(coverage), ledger_unchanged=True)))
