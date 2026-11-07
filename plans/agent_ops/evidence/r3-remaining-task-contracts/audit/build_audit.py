"""Read retained proof; no product imports, tests, services or credentials."""
from pathlib import Path
import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPOS = {
    'Nexus': Path('D:/Projetos/Techridy/okto_labs_okto_nexus'),
    'Connector': Path('D:/Projetos/Techridy/okto-nexus-connector'),
}
HEAD = '412f47056308782e2a5a1f748be9f59c6fd0bf7a'
INPUTS = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, repository='Nexus'):
    file = REPOS[repository] / path
    data = file.read_bytes()
    INPUTS[(repository, path)] = dict(repository=repository, path=path,
        bytes=len(data), sha256=sha(data))
    return data


def load(path, repository='Nexus'):
    return json.loads(read(path, repository))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source(path, symbol=None, repository='Nexus'):
    data = read(path, repository)
    result = dict(repository=repository, path=path, sha256=sha(data))
    if symbol and Path(path).suffix == '.py':
        tree = ast.parse(data.decode('utf-8-sig'))
        nodes = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and node.name == symbol]
        assert nodes, (path, symbol)
        result.update(symbol=symbol, line=nodes[0].lineno)
    elif symbol:
        lines = data.decode('utf-8-sig').splitlines()
        matches = [index+1 for index, text in enumerate(lines)
                   if re.search(r'\b(?:function|class)\s+' + re.escape(symbol) + r'\b', text)]
        assert matches, (path, symbol)
        result.update(symbol=symbol, line=matches[0])
    return result


def xml_proof(path, names, meaning, expected_sha=None):
    data = read(path)
    if expected_sha:
        assert sha(data) == expected_sha, path
    all_cases = list(ET.fromstring(data).iter('testcase'))
    selected = []
    for name in names:
        found = [case for case in all_cases if case.get('name') == name]
        assert len(found) == 1, (path, name, len(found))
        case = found[0]
        assert all(case.find(tag) is None for tag in ('failure', 'error', 'skipped')), (path, name)
        selected.append(dict(classname=case.get('classname'), name=name, status='PASS'))
    return dict(path=path, sha256=sha(data), cases=selected, meaning=meaning,
                verification='Parsed retained XML only; not rerun in this audit.')


def main():
    plan_path = 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
    plan = read(plan_path).decode('utf-8').splitlines()
    ledger = load('plans/agent_ops/ledger.json')
    selected_ids = [key for key, task in ledger['tasks'].items() if task['status'] == 'IMPLEMENTED']
    assert set(selected_ids) == {'BASE-06', 'SVC-07', 'DX-04', 'DX-08', 'DX-15',
                                'DX-16', 'DX-17', 'DX-18', 'DX-20'}
    previous = load('plans/agent_ops/evidence/r3-task-reconciliation/dx/matrix.json')
    old = {row['id']: row for row in previous['tasks']}
    read('plans/agent_ops/evidence/r3-dx-final-contracts/audit/matrix.json')
    read('plans/agent_ops/evidence/r3-service-restart-contracts/milestone.md')
    client_qualification = load('plans/agent_ops/evidence/r3-two-existing-mcp-clients/qualification.json')
    read('plans/agent_ops/evidence/r3-two-existing-mcp-clients/milestone.md')

    definitions = {
        'BASE-06': dict(lines=[245], recommendation='IMPLEMENTED',
            conclusion='Inventário e alvo inicial existem. A medição explícita instalação→primeira sessão útil ainda falta; 7,811s mede apenas liveness HTTP.',
            missing='Medir as etapas de primeiro uso útil no harness suportado e contexto escolhidos; preservar os tempos e pré-requisitos reais. Nenhuma nova infraestrutura de lifecycle é pedida.',
            gate='Cláusula própria da linha245, não M1 herdado por associação. Pode integrar a mesma campanha M1 autorizada, sem campanha redundante.',
            stale='Não substituir esta medida por quantidade de testes, initialize MCP ou resultado de peer sintético.'),
        'SVC-07': dict(lines=[325, 327, 329], recommendation='IMPLEMENTED',
            conclusion='Drain/força explícita/autoridade atual/timeout pendente e retenção de recursos estão comprovados. O novo T22 prova filho real e parada cooperativa, não logout/shutdown externo.',
            missing='Qualificar a cláusula de encerramento externo da linha327 no contexto de gerenciador escolhido, com persistência/estado incerto e reconciliação honestos. O alcance real SVC-T21 permanece aberto.',
            gate='A pendência é external-shutdown/service context; trabalho pago de provedor, preset M1 e participação M2 não são gates deste contrato.',
            stale='Não descrever force como ausente. Não promover encerramento externo usando T22 ou signal.raise_signal no processo controlado.'),
        'DX-04': dict(lines=[409, 411, 413], recommendation='IMPLEMENTED',
            conclusion='Importação protegida, vault, isolamento do ambiente filho, Bearer/origem e negativos estão provados separadamente. Não há prova da ligação completa pelo ParticipantLaunch distribuído até cliente real.',
            missing='Exercitar o launcher suportado com perfil isolado, chave sintética existente e mecanismo protegido; observar autenticação do processo real e o negativo sem referência. Cofre pode conter apenas credencial sintética. Um turno pago não é requisito dessa prova.',
            gate='Gate concreto de entrega/consumo da credencial. GUI/TUI não suportada e cooperação/handoff pertencem a seus escopos; não exigir M1/M2 integral para DX04.',
            stale='412f4705 prova clientes reais com token recebido por helper programático, sem vault/ParticipantLaunch. Não resolve esta integração e não deve ser rotulado como launcher Claude/Codex.'),
        'DX-08': dict(lines=[460], recommendation='IMPLEMENTED',
            conclusion='Consentimentos separados e cadeia canônica do smoke têm provas de contrato. 412f4705 acrescenta troca dirigida/reconnect com Inspector/FastMCP reais; handoff via fachada opcional ainda não está qualificado.',
            missing='Concluir a campanha já em preparação de handoff com consentimento separado, cliente real, claim e resultado canônicos exatos observados pela fachada. Não presumir PASS enquanto em implementação.',
            gate='Não há requisito de marcador de modelo ou inferência paga. O literal exige a cadeia canônica; M1 não é gate.',
            stale='A limitação antiga sobre ausência de modelo real é mais ampla que o literal. Preservar NEXUS_CONNECTION_OK e não promovê-lo a cooperação.'),
        'DX-15': dict(lines=[430, 436], recommendation='VERIFIED',
            conclusion='Fachada resolve topologia, inicia/reutiliza serviço, usa revisão/Finish/preset canônicos e entra no trabalho somente após configuração. Reconnect mantém binding/identidade e não repete wizard/efeitos.',
            missing=None,
            gate='Retirar M1 inteiro como gate deste contrato de encaminhamento. DX17/18/20 e DX-T39/T40/T43 continuam abertos nos seus próprios alcances; não declarar provider ou serviço registrado qualificado.',
            stale='Subscopes genéricos de renovação IN_PROGRESS são superados pela renovação HTTP/IPC/WSS e rotação já verificadas. Não reimplementar esse fluxo.'),
        'DX-16': dict(lines=[432], recommendation='VERIFIED',
            conclusion='Descoberta/recomendação passiva, escolha única sob ambiguidade, resumo de efeitos/limites e consentimento antes dos efeitos estão provados. O requisito explicitamente separa PATH de qualificação/login.',
            missing=None,
            gate='Não herdar prontidão de provedor/instalação nova M1 como gate da descoberta/revisão. Manter candidatos sintéticos e ausência de login confirmado declarados.',
            stale='A limitação atual exige configuração efetiva de harness real que pertence a DX18/DX-T43. A opção de início no login não torna registro de serviço pré-requisito desta revisão.'),
        'DX-17': dict(lines=[434, 436], recommendation='IMPLEMENTED',
            conclusion='IDs/revisões/recibos, etapas honestas, resposta perdida e ausência de replay estão provados. A cláusula própria de primeira solicitação real acompanhada conforme DX20 não foi qualificada.',
            missing='Percurso real de primeira solicitação/estado/decisão/resultado no harness selecionado, local e via Connector aplicável, reutilizando os controles existentes. Nenhum novo histórico ou protocolo é necessário.',
            gate='Ligação expressa da linha434 a DX20; não promover com initialize ou peer sintético. Reusar a campanha M1, sem repetir seus casos puros já verdes.',
            stale='Não listar recovery/renovação ou todo restart como ausência de produto. T23/T24 agora qualificam crash/retorno real Server com trabalho nativo anterior fechado.'),
        'DX-18': dict(lines=[524, 531, 532, 533, 534, 535, 537], recommendation='IMPLEMENTED',
            conclusion='Preset versionado, identidade/workspace/autoridade, configuração conservadora e Finish são implementados e exercitados. A configuração efetiva no processo real é exigência textual explícita.',
            missing='Comprovar instruções/modelo/ferramentas/limites efetivos no processo real lançado pelo serviço e utilidade do preset no trabalho autorizado, sem ampliar permissões ou substituir instruções.',
            gate='Linha531 e utilidade da linha524 justificam a qualificação real. DX-T43 e M1 são pertinentes; não inferir prova de configuração efetiva a partir de serialização ou callback sintético.',
            stale='Renovação remota/rotação/bootstrap não estão ausentes; limitar a pendência ao uso/configuração efetiva reais.'),
        'DX-20': dict(lines=[543, 545, 547, 549, 551], recommendation='IMPLEMENTED',
            conclusion='Fachada canônica de trabalho/continuação/decisões/resultados/reopen e segurança de retry está exercitada. Caminho padrão qualificado real segue ausente.',
            missing='Qualificar DX-T39/T40 e configuração efetiva DX-T43: trabalho, pergunta/permissão representativa, resultado correlacionado e reencontro no terminal sem dashboard/configuração manual.',
            gate='O próprio ID exige caminho padrão qualificado, e a linha551 impede aceitar só processo/sessão pronta. M1 aqui é requisito próprio, não associação.',
            stale='A limitação que lista DX-T45/T46/T47/T50 como pendentes está desatualizada: esses contratos já estão VERIFIED. Isso não encerra T39/T40/T43.'),
    }

    assertions = {
        'DX-04': 'Chave nunca é ecoada; redirect HTTP real não encaminha Bearer; subprocesso recebe referência sem mudar o ambiente pai; vault Windows compensa e repete remoção ausente sem nova chave.',
        'DX-08': 'Troca não autoriza handoff; peer/parent/escopo/claim/resultado exatos são exigidos; texto legado ou unrelated reply não qualificam.',
        'DX-15': 'Connect deixa processo serviço ativo e reutiliza PID/geração; entrada em work exige checkpoint done; Connector reread usa binding atual sem rewrite/reprepare; mesma raiz conclui Finish uma vez sob perdas/rereview.',
        'DX-16': 'Uma candidata recomenda sem subprocesso/pergunta; ambiguidade pergunta uma vez e preserva candidata; resumo precede efeitos e inclui limites; identidade/configuração persistem no reconnect.',
        'DX-17': 'Perda em check/test/Finish recupera o mesmo efeito; cache perdido não reenvia teste; sessão pronta não equivale a resultado; mesma submissão recupera operação sem redispatch.',
        'DX-18': 'Finish cria apenas uma identidade revisada; recovery não gira chave; colisão não adota identidade; falha tardia rollback; bootstrap/filhos/revisão/Finish remoto permanecem correlacionados.',
        'DX-20': 'Interação pergunta/resposta/resultado/retorno usa sessão canônica; decisão perdida recupera resultado sem persistir respostas no perfil; sair do observador não fecha ou interrompe trabalho; reopen não cria história paralela.',
    }
    rows = []
    for task_id in selected_ids:
        definition = definitions[task_id]
        row = dict(id=task_id, ledger_status='IMPLEMENTED',
            title=ledger['tasks'][task_id]['title'],
            literal=[dict(line=line, text=plan[line-1]) for line in definition['lines']],
            recommendation=definition['recommendation'], conclusion=definition['conclusion'],
            minimal_remaining_evidence=definition['missing'], gate_analysis=definition['gate'],
            stale_or_overbroad_limit=definition['stale'],
            product_gap='Nenhuma nova lacuna concreta de produto demonstrada nesta auditoria finita.',
            current_ledger_limitations=ledger['tasks'][task_id].get('limitations', []),
            sources=[], proofs=[])
        if task_id in old:
            previous_task = old[task_id]
            for item in previous_task['sources']:
                ref = source(item['path'], item.get('symbol'), item.get('repository', 'Nexus'))
                ref['prior_audit_sha256'] = item['sha256']
                ref['unchanged_since_prior_audit'] = ref['sha256'] == item['sha256']
                row['sources'].append(ref)
            for item in previous_task['tests']:
                evidence = item.get('passed_evidence')
                if not evidence:
                    continue
                proof = xml_proof(evidence['path'], evidence['passed_cases'], assertions[task_id], evidence['sha256'])
                proof['test_source'] = source(item['path'], item['symbol'], item['repository'])
                proof['test_source']['prior_audit_sha256'] = item['sha256']
                proof['historical_scope_note'] = ('Retained installed campaign qualifies its original fixture/product scope. '
                    'Current source hash is recorded separately; source evolution does not turn an old run into a new run.')
                row['proofs'].append(proof)
        rows.append(row)
    by_id = {row['id']: row for row in rows}

    baseline = load('plans/agent_ops/evidence/baseline-startup.json')
    read('plans/agent_ops/baseline.md')
    by_id['BASE-06']['proofs'].append(dict(path='plans/agent_ops/evidence/baseline-startup.json',
        cold_empty_home_http_liveness_seconds=baseline['cold_empty_home_http_liveness_seconds'],
        provider_invocations=baseline['provider_invocations'],
        missing_measurement='Installation-to-first-useful-harness-session/result'))

    svc = by_id['SVC-07']
    svc['sources'] = [source('src/okto_nexus/bootstrap/server_shutdown.py', 'ServerShutdownCoordinator'),
                      source('src/okto_nexus/bootstrap/runtime_host.py', 'EmbeddedRuntimeHost')]
    svc_xml = 'plans/agent_ops/evidence/r3-cooperative-drain/installed/nexus-installed-v1/canonical/tests.xml'
    svc['proofs'].append(xml_proof(svc_xml, [
        'test_timeout_does_not_start_shutdown_or_reopen_admission',
        'test_force_requires_an_existing_expired_drain',
        'test_cancelled_observer_keeps_drain_owned_and_control_available',
        'test_service_force_checks_authority_generation_and_prior_drain',
        'test_supervisor_latch_failure_prevents_even_explicit_force',
        'test_core_revision_change_during_sql_read_invalidates_quiescent_proof',
        'test_safety_shutdown_escalates_same_owner_without_operator_force',
    ], 'Timeout retains owner/admission fence; force is explicit/current-generation/expired-drain bound; cancelled observation and changed revision cannot manufacture quiescence; safety escalation is distinct.'))
    svc['proofs'].append(xml_proof(svc_xml, [
        'test_signal_keeps_serve_process_and_http_until_inventory_release[signal-SIGINT]',
        'test_signal_keeps_serve_process_and_http_until_inventory_release[signal-SIGTERM]',
    ], 'Real disposable serve process receives signal.raise_signal from its test-owned control pipe; HTTP and uncertainty remain until inventory release. This does not observe actual OS logout/shutdown.'))
    for path in ('tests/test_service_drain_decision.py', 'tests/execution_r4/test_server_signal_shutdown.py'):
        read(path)
    read('plans/agent_ops/evidence/r3-cooperative-drain/qualification.json')
    read('plans/agent_ops/evidence/r3-cooperative-drain/milestone.md')
    svc['proofs'].append(xml_proof('plans/agent_ops/evidence/r3-service-restart-contracts/installed/canonical/tests.xml',
        ['test_restart_pending_keeps_real_connector_child_claim_and_slot'],
        'Current T22: real Core-owned child, claim/slot retained while restart pending; one effect, explicit close, child exit0 and Server DRAINED. No external-shutdown or owner-death-survival claim.'))

    native_path = 'plans/agent_ops/evidence/pr04-participant-launch-native.json'
    native = load(native_path)
    read('plans/agent_ops/evidence/pr04-participant-launch.md')
    read('docs/terminal-participant.md')
    by_id['DX-04']['proofs'].append(dict(path=native_path,
        versions=sorted({(case['client'], case['version']) for case in native['cases']}),
        scope='Retained native protocol-mode present/absent-reference cases using generated Core config and installed environment/context helpers; dummy provider credentials, no turn. Not ParticipantLaunch.apply plus OS vault end-to-end.',
        version_boundary='Claude Code2.1.317 and Codex0.166.0 only. --no-daemon is an intentional current product fence and prior help/schema were inspected in that campaign. No new native command was executed; no inference about other versions.'))
    by_id['DX-04']['client_barrier'] = dict(
        participant_launch='ParticipantLaunch._setup rejects generic; only claude/codex are in participant_process.ADAPTERS.',
        codex='launch_context uses --no-daemon, selected loaded config path and current client context. It refuses silent shared-daemon fallback.',
        inspector_fastmcp='412f4705 helpers construct the real distributed clients and pass fixture token in memory/pipe. They are not supported by this foreground launcher; do not mislabel a wrapper as Claude/Codex.',
        safe_next_step='Plan a selected supported native-client startup with disposable config/trust and synthetic Nexus key, no model turn. Effective context/trust still requires review; no execution is authorized by this audit.')
    by_id['DX-04']['sources'].append(source('src/okto_nexus/adapters/outbound/participant_process.py', 'launch_context'))

    new_client_proof = xml_proof('plans/agent_ops/evidence/r3-two-existing-mcp-clients/installed/canonical/tests.xml',
        ['test_inspector_and_fastmcp_participate_and_reconnect_without_duplicate_identity'],
        'Inspector0.21.2/SDK1.29 and FastMCP2.14.7/SDK1.30: real TCP useful sessions, directed request/reply+ack, reconnect with same identities/sessions. No handoff smoke, model or vault/launcher proof.')
    new_client_proof['test_source'] = source('tests/execution_r4/test_two_existing_mcp_clients.py',
        'test_inspector_and_fastmcp_participate_and_reconnect_without_duplicate_identity')
    by_id['DX-08']['proofs'].append(new_client_proof)
    by_id['DX-08']['work_in_progress'] = 'Parent reports source2/2 PASS (participation plus handoff), with installed session39625 still running. Those files/results are deliberately excluded from this finite audit; no installed PASS is inferred. Recommendation is conditional on closing that separate campaign.'
    by_id['DX-17']['proofs'].append(xml_proof('plans/agent_ops/evidence/r3-service-restart-contracts/installed/canonical/tests.xml',
        ['test_server_restart_preserves_remote_binding_limits_and_invalid_grant[expired]',
         'test_server_restart_preserves_remote_binding_limits_and_invalid_grant[revoked]',
         'test_server_restart_preserves_remote_binding_limits_and_invalid_grant[valid]'],
        'Real Server owner death/replacement and Connector return retain identity/binding/limits and do not replay prior completed work. Previous native session is closed; peers are synthetic. Not first-useful-provider qualification.'))

    reconciliation = dict(
        complete_literal_contracts=['DX-15', 'DX-16'],
        retain_implemented=['BASE-06', 'SVC-07', 'DX-04', 'DX-08', 'DX-17', 'DX-18', 'DX-20'],
        remaining_categories={
            'real_first_use_or_effective_native_configuration': ['BASE-06', 'DX-17', 'DX-18', 'DX-20'],
            'actual_external_shutdown_context': ['SVC-07'],
            'supported_launcher_real_client_credential_chain': ['DX-04'],
            'external_client_optional_handoff_smoke': ['DX-08'],
        },
        documentary_repairs_only=[
            'DX15/DX16: remove blanket M1 gate from task contract, preserve M1/DX17/18/20 and service platform gates separately.',
            'DX15/17/18/20: stale generic renewal labels do not mean remote renewal/rotation is missing.',
            'DX20: DX-T45/T46/T47/T50 are already VERIFIED contract predicates; pending real routes are T39/T40 and effective configuration T43.',
            'DX04: no paid-model requirement; do not demand arbitrary GUI/TUI paths or DX08 cooperation to prove credential delivery.',
            'DX08: model marker/paid inference is not required; only canonical separately consented chain can qualify.',
        ],
    )
    report = dict(format='r3-nine-implemented-readonly-audit.v1', nexus_head=HEAD,
        plan_path=plan_path, plan_sha256=sha(read(plan_path)),
        ledger_sha256=sha(read('plans/agent_ops/ledger.json')),
        scope='Exactly nine tasks with IMPLEMENTED status at 412f4705; task-level recommendations only.',
        method='Read literal plan paragraphs, current named source/test oracles and retained installed XML. Parse the named PASS cases and preserve historical campaign scope; never infer qualification from totals or milestone association.',
        no_test_runs=True, no_service_or_provider_start=True, no_credentials_read=True,
        no_checkout_or_ledger_edits=True, recommendations_applied=False,
        tasks=rows, reconciliation=reconciliation,
        current_installed_package_scope=client_qualification['packages'],
        limits=[
            'This audit does not close M1/M2, service logon/logout/reboot, real providers or an unsupported GUI/TUI.',
            'A contract VERIFIED recommendation is bounded to its stated behavior and retained evidence; no blanket platform/product acceptance follows.',
            'Historical XMLs remain unchanged and failed/superseded runs are not rewritten or counted as PASS.',
            'No assessment of the in-progress external-client handoff campaign is included.',
        ])
    # Compact repeated references without discarding exact testcase identities.
    # Complete file hashes remain in input-manifest.json.
    catalog = {}
    for row in rows:
        if row['id'] in assertions:
            row['contract_oracles'] = assertions[row['id']]
        for reference in row['sources']:
            reference.pop('sha256', None)
            reference.pop('prior_audit_sha256', None)
        for proof in row['proofs']:
            if 'cases' not in proof:
                continue
            path = proof['path']
            entry = catalog.setdefault(path, dict(id='E' + str(len(catalog)+1).zfill(2),
                path=path, sha256=proof['sha256'], cases={}))
            ids = []
            for case in proof['cases']:
                name = case['classname'] + '::' + case['name']
                if name not in entry['cases']:
                    entry['cases'][name] = dict(id=entry['id'] + ':' + str(len(entry['cases'])+1),
                        name=name, status='PASS')
                ids.append(entry['cases'][name]['id'])
            retained = dict(evidence=entry['id'], cases=ids)
            if proof['meaning'] != assertions.get(row['id']):
                retained['meaning'] = proof['meaning']
            if 'test_source' in proof:
                retained['test_source'] = {key:value for key,value in proof['test_source'].items()
                    if key in ('repository', 'path', 'line', 'symbol')}
            proof.clear()
            proof.update(retained)
    report['evidence_catalog'] = [dict(id=entry['id'], path=entry['path'], sha256=entry['sha256'],
        cases=list(entry['cases'].values())) for entry in catalog.values()]
    report['historical_scope_note'] = ('Each named retained XML case was checked PASS. Historical installed '
        'campaigns qualify their original fixture/product scope; current source references are read-only '
        'anchors with hashes in input-manifest.json, not new executions. Counts are not summed as coverage.')
    dump(ROOT / 'matrix.json', report)
    dump(ROOT / 'input-manifest.json', dict(inputs=sorted(INPUTS.values(), key=lambda r:(r['repository'],r['path']))))

    summary = [
        '# Auditoria finita das nove tarefas IMPLEMENTED', '',
        'Base: Nexus `412f47056308782e2a5a1f748be9f59c6fd0bf7a`. Somente leitura; nenhum teste, serviço, provedor ou credencial acessado. Requisitos literais, fontes, casos PASS exatos e hashes estão em `matrix.json` e `input-manifest.json`.', '',
        '| ID | Recomendação | Evidência ainda necessária / limite |',
        '|---|---|---|',
    ]
    for row in rows:
        summary.append('| ' + row['id'] + ' | ' + row['recommendation'] + ' | ' +
            (row['minimal_remaining_evidence'] or 'Nenhuma falta concreta no contrato literal. ' + row['gate_analysis']) + ' |')
    summary += ['', 'DX-15 e DX-16 podem ser reconciliados como contratos VERIFIED sem fechar M1. '
        'Os outros sete conservam pendências específicas; nenhum novo defeito de produto foi demonstrado.', '',
        '412f4705 acrescenta participação/troca dirigida/reconnect de Inspector e FastMCP reais. '
        'Não junta ParticipantLaunch/vault nem executa o handoff opcional. Root reportou2/2 fonte em nova campanha, mas a instalação ainda estava rodando na sessão39625; esse resultado não foi promovido nesta matriz.', '',
        'SVC-T22 prova a parada pendente com filho real; não substitui logout/shutdown externo. '
        'DX-T45/T46/T47/T50 e renovação remota já têm contratos próprios qualificados; '
        'sua menção genérica como ausência deve ser removida, mantendo T39/T40/T43.', '',
        'A pendência DX04 não pressupõe inferência paga: exige demonstrar o consumo da credencial pelo cliente suportado real. '
        'O launcher atual só aceita Claude/Codex e rejeita generic; os helpers Inspector/FastMCP não podem ser renomeados como esses clientes. '
        'As versões nativas previamente documentadas são Claude2.1.317/Codex0.166.0, em modo de protocolo isolado; nenhuma versão nova foi executada.', '']
    (ROOT / 'summary.md').write_text('\n'.join(summary), encoding='utf-8')
    names = ['matrix.json', 'input-manifest.json', 'summary.md', 'build_audit.py']
    entries = [dict(path=name, bytes=(ROOT/name).stat().st_size,
                    sha256=sha((ROOT/name).read_bytes())) for name in names]
    dump(ROOT / 'artifact-manifest.json', dict(format='public-allowlist.v1', artifacts=entries,
        contains='Only public audit, exact source/evidence references and hashes; no copied database, profile, secret or process log.',
        input_count=len(INPUTS), task_count=len(rows), tests_executed=0))
    print(json.dumps(dict(path=str(ROOT), tasks=len(rows), input_files=len(INPUTS),
        recommendations=reconciliation['complete_literal_contracts'],
        matrix_sha256=sha((ROOT/'matrix.json').read_bytes()),
        manifest_sha256=sha((ROOT/'artifact-manifest.json').read_bytes()))))


if __name__ == '__main__':
    main()
