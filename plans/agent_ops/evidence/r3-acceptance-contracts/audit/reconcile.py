"""Finite read-only acceptance audit. This is an evidence parser, not a test run."""
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).parent
REPOS = {'nexus': ROOT, 'connector': ROOT.parent / 'okto-nexus-connector',
         'core': ROOT.parent / 'okto-nexus-connector-core'}
BASE = 'plans/agent_ops/evidence/'
inputs = {}
proofs = {}
xml_checks = []
source_comparisons = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path, repository='nexus', **extra):
    repository = repository.lower()
    full = REPOS[repository] / path
    item = dict(repository=repository, path=path, sha256=digest(full), bytes=full.stat().st_size)
    inputs[(repository, path)] = item
    return item | extra


def load(path):
    ref(path)
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def retained_xml(path, names, classname=None, expected_hash=None):
    meta = ref(path)
    if expected_hash:
        assert meta['sha256'] == expected_hash, (path, 'retained report changed')
    nodes = []
    for case in ET.parse(ROOT / path).iter('testcase'):
        name = case.get('name', '')
        if not any(name == wanted or name.startswith(wanted + '[') for wanted in names):
            continue
        if classname is not None and case.get('classname') != classname:
            continue
        assert not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped'))
        nodes.append(case.get('classname', '') + '::' + name)
    for name in names:
        assert any(node.split('::', 1)[1] == name or node.split('::', 1)[1].startswith(name + '[') for node in nodes), (path, name)
    item = meta | dict(passed_nodes=sorted(nodes), interpretation='Existing retained PASS; no new execution.')
    xml_checks.append(item)
    return item


def source(item):
    current = ref(item['path'], item.get('repository', 'nexus'))
    previous = item.get('sha256')
    match = previous is None or current['sha256'] == previous
    source_comparisons.append(dict(path=item['path'], repository=current['repository'], current_sha256=current['sha256'], catalog_sha256=previous, equal=match))
    return current | dict(symbol=item.get('symbol', item.get('test')), line=item.get('line'), catalog_sha256=previous, same_bytes_as_catalog=match)


ledger = load('plans/agent_ops/ledger.json')
plan = ref('PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md')
assert plan['sha256'] == ledger['plan_sha256']
text = (ROOT / plan['path']).read_text(encoding='utf-8').splitlines()
dx = load(BASE + 'r3-task-reconciliation/dx/matrix.json')
svc = load(BASE + 'r3-task-reconciliation/svc/audit.json')
atn = load(BASE + 'r3-task-reconciliation/atn-obs/matrix.json')
inv = load(BASE + 'r3-invariant-reconciliation/matrix.json')

def dxproof(key, symbol):
    found = [t for task in dx['tasks'] for t in task['tests'] if t['symbol'] == symbol]
    assert found, symbol
    t = found[0]
    report = t['passed_evidence']
    proofs[key] = dict(source=source(t), assertions=t['assertions'],
                       report=retained_xml(report['path'], report['passed_cases'], expected_hash=report['sha256']))


for key, symbol in {
    'identity': 'test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key',
    'reconnect_identity': 'test_default_cli_review_is_stable_and_reconnect_preserves_identity_customizations',
    'remote_setup': 'test_operator_and_connector_cli_complete_same_root_once',
    'terminal_work': 'test_interactive_cli_request_question_answer_result_and_return',
    'terminal_resume': 'test_send_result_reopen_continue_and_close_share_canonical_session',
    'lost_submission': 'test_lost_submission_response_recovers_same_work_without_duplicate_dispatch',
    'lost_decision': 'test_native_decision_response_loss_recovers_canonical_result_and_keeps_answers_out_of_profile',
    'terminal_detach': 'test_leaving_interactive_cli_does_not_interrupt_or_close_service_owned_work',
    'preset_merge': 'test_review_advances_only_unchanged_defaults_and_finish_recovers_once',
    'preset_disabled': 'test_disabled_runtime_stays_disabled_without_test_or_grant',
    'dashboard': 'test_dashboard_personalization_and_terminal_reopen_preserve_identity_history_and_grants',
    'revocation': 'test_remote_revocation_keeps_recovered_receipt_historical_and_participant_cannot_renew',
    'participant_preserve': 'test_review_apply_reconnect_preserves_runtime_and_other_configuration',
}.items():
    dxproof(key, symbol)

for key in ('E01', 'E02', 'E03', 'E06', 'E08', 'E10', 'E14', 'E15', 'E16'):
    e = svc['evidence'][key]
    proofs[key] = dict(assertion=e['assertion_read'], limit=e['limits'], reports=[
        retained_xml(t['report'], [t['name']], t['classname']) for t in e['retained_passes']], sources=[
        source(s) for t in e['current_test_sources'] for s in t['locations']])

for key, node in {
    'obs_canonical': 'tests/test_observation_service.py::test_publish_changes_no_coordination_presence_or_capacity',
    'obs_work': 'tests/execution_r4/test_external_observation_isolation.py::test_external_done_and_seen_do_not_release_a_turn_or_wake_queued_work',
    'obs_idle': 'tests/execution_r4/test_external_idle_scheduler_isolation.py::test_external_idle_preserves_exact_unconsumed_claim_reservation',
    'atn_passive': 'tests/test_attention_operations.py::test_read_is_metadata_only_and_changes_no_table',
    'mixed': 'tests/execution_r4/test_r3_mixed_coordination.py::test_rg01_two_mcp_participants_and_one_runtime_cooperate_without_new_identities',
}.items():
    t = atn['test_proofs'][node]
    r = t['selected_passing_report']
    proofs[key] = dict(source=ref(t['source'], line=t['line'], symbol=t['name']), assertions=t['assertions'],
        report=retained_xml(r['path'], [t['name']], expected_hash=r['sha256']), limit=t['qualification_note'])

proofs['remote_no_fallback'] = dict(source=ref('tests/execution_r4/test_remote_operator_terminal.py'),
    report=retained_xml(BASE+'pr03-remote-operator-installed.xml', ['test_remote_profile_reuse_selects_remote_before_any_local_service']),
    assertion='Saved remote operator profile is resolved before local service path; no local start/fallback.')
proofs['drain'] = dict(source=ref('tests/execution_r4/test_service_cooperative_drain.py'),
    report=retained_xml(BASE+'r3-cooperative-drain/installed/nexus-installed-v1/canonical/tests.xml', ['test_drain_keeps_approval_and_terminal_publication_until_work_completes']),
    assertion='Drain retains admitted approval/control/terminal publication; participant cannot decide; drift invalidates current authority.')
proofs['self_approval'] = dict(source=ref('tests/execution_r4/test_terminal_policy.py'),
    report=retained_xml(BASE+'pr03-terminal-policy-installed.xml', ['test_participant_cannot_initialize_server_policy']),
    assertion='Participant cannot initialize or bypass human decision policy.')
proofs['limits'] = dict(source=ref('tests/execution_r4/test_terminal_authorization.py'),
    report=retained_xml(BASE+'pr03-terminal-authorization-installed.xml', ['test_renewal_is_explicit_bounded_and_new_opening_uses_new_grant', 'test_renewal_does_not_rebind_or_close_an_exhausted_live_session']),
    assertion='Explicit bounded grant, no silent authority expansion; exhausted live session cannot send under replacement grant.')

document_refs = {
    'herdr': BASE+'pr09-herdr.md',
    'herdr_manifest': BASE+'pr09-herdr/artifact-manifest.json',
    'joint': BASE+'r3-joint-contracts/integration.json',
    'drain_qualification': BASE+'r3-cooperative-drain/qualification.json',
    'accepted_invariants': BASE+'r3-invariant-reconciliation/accepted.json',
    'formats': BASE+'pr04-participant-contract-client-formats.json',
    'initialize': BASE+'pr04-participant-launch-native.json',
    'client_driver': 'plans/agent_ops/campaigns/participant-environment.py',
    'browser': BASE+'pr03-project-dashboard-browser.json',
    'baseline': BASE+'baseline-startup.json',
    'native_proposal': BASE+'r3-qualification-readiness/native-proposal/native-service-campaign-proposal.json',
    'traceability': BASE+'r3-compatibility-boundaries/traceability/traceability.json',
}
documents = {key: ref(path) for key, path in document_refs.items()}
implementation = []
for task_id in ('DX-18', 'DX-20', 'DX-21'):
    task = next(t for t in dx['tasks'] if t['id'] == task_id)
    for item in task['sources']:
        if item['path'] not in [x['path'] for x in implementation]:
            implementation.append(source(item))

rows = []
def row(id, recommendation, reason, keys, docs, missing, safe, limit):
    c = ledger['completion_criteria'][id]
    matches = [i+1 for i, line in enumerate(text) if line.endswith(c['requirement'])]
    assert len(matches) == 1, (id, matches)
    rows.append(dict(id=id, literal_requirement=c['requirement'], plan_line=matches[0], current_status=c['status'],
        proposed_status=recommendation, reason=reason, proof_ids=keys, document_ids=docs,
        remaining_work=missing, safe_implementation_gap=safe, limit=limit))

row('AC-01','NOT_VERIFIED',
    'Os catálogos demonstram implementação/reuso e testes das 59 tarefas; não há novo gap de código identificado. Entretanto o literal é universal sobre tarefas obrigatórias, e entregas de evidência expressamente exigidas ainda faltam; não equivale a exigir que todos os substatus históricos sejam VERIFIED.',
    ['identity','remote_setup','terminal_work','drain','obs_work'], ['traceability','baseline'],
    ['BASE-06, plano245: medir instalação até primeira sessão útil permanece NOT_RUN; 7.811s é liveness foreground e não essa medida.',
     'As campanhas obrigatórias ainda abertas devem manter seus próprios gates: SVC-12/AC-13 serviço real, DX-08/AC-03 participação/cooperação e DX-20/AC-11 ciclo produtivo. Um plano de campanha ou teste sintético não é a entrega executada.'],
    'Nenhum novo produto identificado; trabalho restante é obter/conciliar a evidência exigida, especialmente a medida BASE-06.',
    'Não se usa task.status como prova nem se exige campanha M1 para testes puramente contratuais.')
row('AC-02','VERIFIED',
    'Composição contratual demonstrada: SVC→DX no start/reuse e trabalho possuído; DX→ATN nas decisões/publicações canônicas; ATN→OBS na projeção externa; OBS→execução/coordenação sem interferência. Herdr é opt-in e os caminhos canônicos funcionam com OBS desabilitado. Dependências de contrato estão implementadas sem declarar encerrados os marcos de campanha.',
    ['E16','terminal_detach','drain','atn_passive','obs_work','obs_idle','mixed'], ['joint','herdr','herdr_manifest','drain_qualification'], [],
    'Nenhum. Não criar novo teste monolítico nem gate de provedor por associação.',
    'Windows e composição canônica com pares sintéticos; não é declaração de M1/M2 nem promoção dos critérios de saída reais PR03/04/10.')
row('AC-03','NOT_VERIFIED',
    'Dois formatos/versões e initialize real estão retidos, e dois atores MCP sintéticos cooperam sem novas identidades. As provas não ligam os dois clientes identificados a participação canônica: o driver de cliente injeta chave em ambiente manual e não chama tools/call; RG01 usa dois atores pelo mesmo helper TestClient.',
    ['mixed','participant_preserve'], ['formats','initialize','client_driver'],
    ['Reter participação de dois clientes MCP existentes e identificados: sessões/troca dirigida pelo Server real, autenticação por identidade autorizada, contagem de identidades/bindings estável e nenhum adaptador nativo novo.',
     'Plano399 prefere Claude Code/Codex mas não os obriga; plano454-456 e874 distinguem initialize de participação. AC03 não exige dois harnesses nativos nem inferência paga, nem exige por si só handoff concluído ou cadeia completa de cofre.'],
    'Qualificação segura possível sem produto novo e sem provedor se dois clientes existentes tiverem API/CLI de chamada MCP direta; usar homes e chaves exclusivamente sintéticos e declarar nomes/versões. Não presumir essa capacidade em Claude/Codex sem verificação, nem chamar duas invocações do mesmo helper de dois produtos qualificados.',
    'Não promover o initialize manual a cofre→launcher→cliente; isso continua separado em DX04. Não há execução nova nesta auditoria.')
row('AC-11','NOT_VERIFIED',
    'O percurso terminal, preset, decisões e recuperação estão qualificados com Core/HTTP/SQLite reais e peer nativo sintético. O literal exige harness real em duas topologias.',
    ['E01','E02','identity','terminal_work','terminal_resume','remote_setup','lost_decision'], ['drain_qualification'],
    ['Executar DX-T39 local e DX-T40 via Connector com um harness real suportado: tarefa, progresso, pergunta/permissão, decisão canônica, resultado e retorno ao trabalho; serviço persistente sem dashboard ou terminal exclusivo.',
     'Medir o primeiro uso útil de BASE-06 na campanha; registrar contexto, versões e custos previamente autorizados.'],
    'Nenhuma lacuna nova de produto identificada; campanha real depende de contexto/credencial/autorização apropriados.',
    'Não converter teste de processo, initialize, NEXUS_CONNECTION_OK ou peer sintético em M1.')
row('AC-12','VERIFIED',
    'Concorrência real converge para um owner/PID/generation em cada host; locks impedem segundo owner. Perfil remoto é resolvido antes do lifecycle local. O roteamento de supervisor instalado recusa fallback/definition drift e o foreground tem um único owner.',
    ['E01','E02','E03','E06','E08','remote_no_fallback'], ['accepted_invariants'], [],
    'Nenhum; não exigir login/registro real do agendador para este contrato de exclusividade.',
    'Concorrência/locks em processos Windows reais; efeitos do Task Scheduler injetados nos testes de roteamento. Instalação/login reais continuam AC13.')
row('AC-13','NOT_VERIFIED',
    'Lifecycle/instalação idempotente/contexto salvo e upgrades têm provas reais e injetadas discriminadas; a sequência de serviço registrado e contexto de credenciais reais não foi executada.',
    ['E08','E10','E14','E15'], ['native_proposal'],
    ['Na plataforma Windows declarada: registrar/iniciar no login, parar sem ressurreição, recuperar crash/backoff, remover e comprovar contexto/cwd/PATH e credenciais no serviço real.',
     'Manter login, logout, reboot, terminal fechado e suspensão como eventos distintos. Não declarar outras plataformas qualificadas.'],
    'Campanha explícita de ambiente, sem novo framework ou mecanismo de supervisor.',
    'Mocks de Task Scheduler e processo foreground supervisionado não substituem logon real; cofre sintético não comprova credencial pessoal real.')
row('AC-14','NOT_VERIFIED',
    'Recuperação canônica, perda de resposta, revogação e ownership/incerteza já têm asserts; restart e transporte não autorizam repetir efeito ou renovar grant. O predicado suspensão/retorno ainda não tem campanha retida.',
    ['E01','E02','lost_submission','lost_decision','revocation','limits','drain'], ['joint','drain_qualification'],
    ['Executar/observar suspensão e retorno reais com operação/owner conhecido; validar que ausência de resposta não vira morte, trabalho repetido, autoridade renovada ou release de claim.',
     'SVC-T23/T24 ainda têm anotação de mapeamento/qualificação descartável: mapear continuidade restart/Server drop específico antes de exigir ambiente real extra. Essas lacunas não autorizam inferir necessidade de provedor.'],
    'Nenhuma correção de produto demonstrada; eventual qualificação descartável de continuidade é menor que M1. Suspensão real é limite ambiental restante.',
    'Falhas injetadas e recovery após commit comprovam seus cortes exatos; não são suspensão/logout/reboot observados.')
row('AC-16','VERIFIED',
    'Identidade persistente e preset generalista são objetos canônicos revisados; coordenação é limitada ao workspace/permissões concedidos. harness_settings vazio conserva modelo/instruções/sandbox, tool_access=ask conserva decisões, grants são limitados. Merge preserva customizações; agente não inicializa política nem aprova seus pedidos.',
    ['identity','reconnect_identity','remote_setup','preset_merge','preset_disabled','self_approval','limits','drain'], ['accepted_invariants'], [],
    'Nenhum no literal de preservação/autoridade. Não herdar DX-T43 ou M1 como requisito novo deste AC.',
    'Preservação e enforcement das opções suportadas qualificados; não mede utilidade de inferência nem afirma consumo de configuração por provedor real. DX-T43 permanece separado. Plano119/524-539 e INV27 definem a preservação, não nova campanha obrigatória AC16.')
row('AC-17','VERIFIED',
    'Reconnect mantém identidade e customizações; merge/upgrade preservam seleção, arquivos e dados; dashboard instalado personaliza os mesmos objetos. Caminho terminal completo e retorno ao trabalho têm decisões/resultados correlacionados sem painel obrigatório.',
    ['reconnect_identity','preset_merge','preset_disabled','dashboard','E14','E15','terminal_work','terminal_resume','revocation'], ['browser'], [],
    'Nenhum; não reabrir gate de M1 real para o contrato de preservação/UX.',
    'Browser real e upgrades instalados, trabalho nativo sintético; isto não encerra AC11 nem qualifica configurações de todos os clientes/providers.')

# All citations are explicitly read; unchanged historical PASS is not a new campaign.
changed = []
for item in inputs.values():
    if digest(REPOS[item['repository']] / item['path']) != item['sha256']:
        changed.append(item['path'])
assert not changed, changed
head = subprocess.check_output(['rtk', 'git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
matrix = dict(format='r3-finite-acceptance-audit', version=1, scope=[r['id'] for r in rows],
    head=head, plan=plan, method='Read-only source/catalog/XML inspection; no tests, services, browser, provider or checkout/ledger edits.',
    proposed_counts={s:sum(r['proposed_status']==s for r in rows) for s in ['VERIFIED','NOT_VERIFIED']},
    rows=rows, implementation=implementation,
    historical_rule='Each node is checked PASS in the exact retained XML; hashes and current source comparison are recorded. Historical result is reused only for its asserted contract and declared fixture scope, never promoted to a new real-client/provider/service campaign.',
    global_acceptance=False, new_test_runs=0, ledger_edits=0, product_edits=0)
verification = dict(input_count=len(inputs), inputs_changed=changed, retained_report_node_pairs=sum(len(x['passed_nodes']) for x in xml_checks),
    source_comparisons=source_comparisons, mismatched_source=[x for x in source_comparisons if not x['equal']], new_executions=0)
for name, payload in [('matrix.json',matrix),('proofs.json',dict(proofs=proofs,documents=documents)),
                       ('input-manifest.json',list(inputs.values())),('verification.json',verification)]:
    (OUT/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary = '''Auditoria finita AC-01/02/03/11/12/13/14/16/17

Recomendação: VERIFIED AC-02, AC-12, AC-16 e AC-17 por seus contratos literais; manter os outros cinco abertos com a pendência específica em matrix.json.

Nenhuma nova lacuna concreta de produto foi demonstrada. AC-01 conserva a entrega BASE-06 de medir o primeiro uso útil, além das campanhas explicitamente obrigatórias. AC-03 é participação canônica de dois clientes testados: não exige inferência paga ou dois adaptadores. A menor qualificação segura pode usar clientes MCP existentes que permitam tools/call direto, em ambiente sintético, sem presumir esse modo em clientes que não o ofereçam. Duas identidades no mesmo helper não qualificam automaticamente dois produtos clientes.

AC-11 depende do harness real local/remoto; AC-13 do serviço registrado/login/contexto real; AC-14 da suspensão/retorno ainda não observados, preservando o trabalho de mapeamento seguro restart/conexão separado. AC-16 é contrato de preservação/autoridade; não recebe automaticamente o gate DX-T43 de consumo efetivo pelo provedor. AC-17 é preservação e completude da interface terminal, não M1 real por associação.

proofs.json contém nodes e afirmações; input-manifest.json contém hashes. verification.json confirma estabilidade e distingue fontes de catálogo de arquivos atuais. Nenhum resultado foi reexecutado, nenhuma campanha sintética virou prova real, nenhum status foi alterado.
'''
(OUT/'summary.txt').write_text(summary,encoding='utf-8')
allowlist=['reconcile.py','matrix.json','proofs.json','input-manifest.json','verification.json','summary.txt']
manifest=dict(public_allowlist=[dict(path=name,sha256=digest(OUT/name),bytes=(OUT/name).stat().st_size) for name in allowlist],
              excluded=['credentials','homes','databases','private fixture files','wheels','raw runtime logs'])
(OUT/'artifact-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(directory=str(OUT),head=head,counts=matrix['proposed_counts'],inputs=len(inputs),
    retained_pairs=verification['retained_report_node_pairs'],source_mismatch=verification['mismatched_source'],
    matrix_sha256=digest(OUT/'matrix.json'),manifest_sha256=digest(OUT/'artifact-manifest.json')),ensure_ascii=False))
