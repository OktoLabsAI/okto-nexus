"""Create a finite preparation-only M1 proposal; never execute its commands."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
NEXUS = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
CORE = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
CONNECTOR = Path('D:/Projetos/Techridy/okto-nexus-connector')
artifact = json.loads((PUBLIC / 'codex-0.157.0-pure-qualification.json').read_bytes())
paths = {
    'campaign_root': str(ROOT / 'campaign'),
    'server_home': str(ROOT / 'campaign/nexus-home'),
    'operator_home': str(ROOT / 'campaign/operator-home'),
    'connector_state': str(ROOT / 'campaign/connector-state'),
    'local_project': str(ROOT / 'campaign/local-project'),
    'remote_project': str(ROOT / 'campaign/connector-project'),
    'private_evidence': str(ROOT / 'campaign/private'),
    'public_evidence': str(ROOT / 'campaign/public'),
    'codex_executable': artifact['native_executable'],
}
sources = [
    (NEXUS, 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'),
    (NEXUS, 'src/okto_nexus/adapters/inbound/cli/connect.py'),
    (NEXUS, 'src/okto_nexus/adapters/inbound/cli/work.py'),
    (NEXUS, 'src/okto_nexus/application/terminal_connection.py'),
    (NEXUS, 'src/okto_nexus/application/terminal_work.py'),
    (NEXUS, 'src/okto_nexus/application/project_preset.py'),
    (NEXUS, 'src/okto_nexus/application/execution_event_views.py'),
    (NEXUS, 'docs/terminal-work.md'),
    (NEXUS, 'docs/remote-project-setup.md'),
    (CONNECTOR, 'src/okto_nexus_connector/cli/main.py'),
    (CORE, 'src/nexus_connector_core/native/adapters/compatibility.py'),
    (CORE, 'src/nexus_connector_core/build_identity.py'),
    (CORE, 'src/nexus_connector_core/discovery.py'),
    (CORE, 'src/nexus_connector_core/harness_configuration.py'),
    (CORE, 'src/nexus_connector_core/native/codex_app_server_0_157_0.schemas.json'),
    (CORE, 'src/nexus_connector_core/native/adapters/codex.py'),
    (CORE, 'plans/implementation/evidence/codex-real-turn-controls-2026-09-26.md'),
    (CORE, 'plans/implementation/evidence/codex-native-questions-0-159-alpha-20261003.md'),
]
snapshots = [{'path': str(base / relative), 'sha256': hashlib.sha256((base / relative).read_bytes()).hexdigest()} for base, relative in sources]

def step(identity, commands, evidence, effects, gate=None):
    return dict(id=identity, commands=commands, required_evidence=evidence, proposed_effects=effects, gate=gate)

proposal = {
    'format': 'okto.m1.codex-real-campaign-proposal', 'revision': 1,
    'status': 'PREPARED_NOT_AUTHORIZED_NOT_EXECUTED',
    'preparation_date': '2026-11-07',
    'intent': 'Qualify the fixed M1 terminal cycle locally and through the Connector, using a real qualified Codex build and a real explicitly authorized account. Synthetic tests and byte identity do not close M1.',
    'authorization': {
        'received': 'Account is already authenticated in Codex CLI; requested aggregate limit is 200000 tokens. These facts inform this proposal only.',
        'inference_authorized': False, 'credential_use_authorized': False, 'service_install_authorized': False,
        'this_preparation_permitted': ['Read repository contracts and historical public evidence', 'Download official release metadata/ZIP to this new Temp root', 'Hash/extract bytes and evaluate pure Core qualification functions'],
        'executed_native_commands': [], 'models_called': 0,
    },
    'source_heads_at_preparation': {
        'nexus': '21c5b7573316a2571a5378e479dbc7511e32fa70',
        'connector': 'fb3fff473ff246adcffa9e91573ac85f7a394170',
        'core': '3cdba87857e25b4ad5bdbaed91647bfa55873f91',
        'qualification': 'Context only: SVC07 uncommitted integration/final packaging is still in progress; these are not final campaign package pins.',
    },
    'package_pins': {name: {'status': 'PENDING_FINAL_SVC07_WHEEL', 'wheel_sha256': None, 'installed_import_sha256': None, 'python_path': None} for name in ('nexus', 'connector', 'core')},
    'paths': paths,
    'native_selection': {
        'personal_cli_observation_from_root': {'version': '0.167.0', 'qualified_for_this_campaign': False, 'reason': 'Current exact-build native request/control allowlists do not qualify this version.'},
        'selected_version': '0.157.0', 'platform': 'Windows x86_64',
        'executable': artifact['native_executable'], 'fingerprint': artifact['fingerprint'],
        'current_build_identity': artifact['build_identity'],
        'qualified_by': artifact['qualified_route'],
        'qualified_native_requests': artifact['native_request_contracts'],
        'required_binding': 'Fresh explicit local selection and canonical approval of this absolute path/project; byte qualification never grants authority.',
        'supporting_proof': 'codex-0.157.0-pure-qualification.json',
        'alternatives_not_selected': [
            {'version': '0.159.0', 'reason': 'Qualified conversation/controls but no qualified native permission/question method; insufficient alone for the requested representative native decision.'},
            {'version': '0.159.0-alpha.12.1', 'reason': 'Qualified requestUserInput only; optional separate exact build, not downloaded or selected for this finite proposal.'},
        ],
        'limits': ['No binary version/help/schema process has been run in this preparation.', 'A matching executable does not independently qualify every bundled helper/DLL or provider-home behavior; the official complete ZIP is retained, without executing installers or sandbox setup helpers.'],
    },
    'topology': {
        'initial_platform': 'Windows, user service context',
        'campaign_lanes': ['Nexus owns local Codex process', 'Connector owns Codex process; separate human OperatorProfile owns decisions'],
        'network': 'Separate isolated processes and homes on loopback for the Connector protocol lane; no claim of a second physical host or cross-host network qualification.',
        'scope': 'Fresh project identities, two scratch workspaces, bounded fixture files, no personal project files.',
        'supervisor': 'Windows user tasks through canonical service/connection commands only after their exact final paths/task names/argv are pinned and approved.',
        'native_service_proposal_reference': str(NEXUS / 'plans/agent_ops/evidence/r3-qualification-readiness/native-proposal/native-service-campaign-proposal.json'),
        'native_service_proposal_limit': 'That retained proposal is historical preparation, not authorization. Do not reuse its old package hashes or register duplicate tasks blindly. SVC07 final pins and task names must be regenerated before execution approval.',
    },
    'provider_context': {
        'provider_home': None, 'status': 'Exact user-approved native authentication context still needs to be pinned without reading its credential contents.',
        'agent_must_not_read': ['auth.json', 'credential stores', 'personal config files', 'personal transcripts'],
        'native_behavior_requiring_authorization': 'The selected native CLI may read its existing login/config and write its own session history or refresh login material. An isolated executable/project is not an isolated authenticated home.',
        'credential_copy': False, 'new_auth_channel': False,
        'effective_model': None,
        'effective_policy': 'Preserve canonically reviewed defaults; record reported model, instructions source, approval policy, sandbox, inherited MCP/tool settings and provider-home selection. Do not assume the service inherited an interactive shell configuration.',
        'decision_gate': 'Use only the qualified commandExecution/requestApproval method. If the actual reviewed policy cannot surface it, stop with this native-decision requirement pending; model text is never substituted.',
    },
    'finite_work': {
        'fixture': {'numbers.csv': 'value\n1\n2\n3\n4\n', 'expected_rows': 4, 'expected_sum': 10},
        'maximum_productive_admissions': 6,
        'allocation': 'At most one local setup test, one remote setup test if the actual canonical path performs it, one useful request and one short explicit continuation per topology. Unused slots stay unused; no extra retry turns to chase a desired approval.',
        'request': 'In this disposable project, inspect numbers.csv, report its row count, sum and SHA-256. Do not install tools, use the network, read outside this project, spawn subagents, or modify personal files. If a native command permission is needed, request it through the native mechanism and wait.',
        'continuation': 'Using only the existing project result, state the sum once. Do not run another command.',
        'native_decision': 'Review one genuine native request per topology. Approve only an exact read/hash/aggregate command confined to the selected scratch project; otherwise deny and stop. A missing request leaves DX-T45 incomplete. No broad command prefix, sandbox bypass or persistent approval.',
        'serial_execution': True, 'parallel_provider_turns': False,
        'connection_tests_count_toward_tokens': True,
    },
    'steps': [
        step('00-package-and-byte-gate', [], 'Final noneditable wheels/import hashes, pure recheck of exact Codex fingerprint, no source mixing; confirm current candidate path and readiness version.', 'No model inference.', 'All final SVC07 packages pinned; artifact/hash still equal; no personal configuration read.'),
        step('01-context-and-service-review', ['<NEXUS> service status --home <server_home> --json', '<CONNECTOR> --state-dir <connector_state> daemon status --json'], 'Review exact owned task names, homes, executable/argv, provider context and initial platform. Use separately approved canonical user-service plan/startup review.', 'Only after explicit authorization: isolated service/task lifecycle; no logout/reboot or personal task changes.', 'Task targets absent or exactly owned; packages and launch context reviewed; token policy clarified.'),
        step('02-local-connect-review-apply', [
            '<NEXUS> connect --profile m1-local --client codex --project <local_project> --candidate-ref <observed_exact_ref> --provider-home <approved_home> --new-agent m1-local --plan <service-selection-args>',
            '<NEXUS> connect --profile m1-local --approve <exact_review_revision> --no-chat --timeout 120 <service-selection-args>'
        ], 'Capture reviewed identity/workspace/preset/effective policy and immutable setup/test/Finish IDs. Local setup test is real inference and belongs in the campaign total.', 'New isolated identity/workspace, reviewed binding/grant and local setup test.', 'Explicit review approval; provider use authorized; usage collection armed before the first setup test.'),
        step('03-local-work-decision-result', [
            '<NEXUS> work send --profile m1-local --request-id m1-local-work-01 --message <finite_work.request> --json <service-selection-args>',
            '<NEXUS> work watch --profile m1-local --timeout 120 --json <service-selection-args>',
            '<NEXUS> work answer --profile m1-local --approval-id <actual_id> --json <service-selection-args>',
            '<NEXUS> work answer --profile m1-local --approval-id <actual_id> --decision <reviewed_approve_or_deny> --review <actual_revision_hash> --json <service-selection-args>'
        ], 'Actual permission current actor/revision/scope, canonical ACK/terminal outcome, correct fixture answer, result reference and complete token cursor.', 'One useful request and at most one tightly reviewed native permission; no automatic reattempt.', 'Real native request, no textual substitute; accounting current and within the agreed operational gate.'),
        step('04-local-return-and-continuity', [
            '<NEXUS> work status --profile m1-local --json <service-selection-args>',
            '<NEXUS> work resume --profile m1-local --json <service-selection-args>',
            '<NEXUS> work send --profile m1-local --request-id m1-local-work-02 --message <finite_work.continuation> --json <service-selection-args>'
        ], 'Exit and reopen only the terminal observer, recover the same request/session/result. No new native session or duplicated productive request for recovery. Continuation is separately explicit and optional only if the existing session remains supported.', 'At most one explicitly requested continuation.', 'Unsupported native context continuation is reported; never fabricate resume or automatically use --new-session.'),
        step('05-connector-root-review-finish', [
            '<CONNECTOR> --state-dir <connector_state> connect --server <loopback_origin> --harness codex_app_server --executable <codex_executable> --project <remote_project> --provider-home <approved_home> --request-id m1-connector-setup --setup-draft <public_host_draft>',
            '<NEXUS> operator login --profile m1-human --server <loopback_origin> --username <approved_human>',
            '<NEXUS> connect --operator-profile m1-human --remote-draft <public_host_draft> --profile m1-remote --plan',
            '<NEXUS> connect --operator-profile m1-human --remote-draft <public_host_draft> --profile m1-remote --approve <exact_review_revision> --setup-receipt-output <public_handoff> --no-chat --timeout 120',
            '<CONNECTOR> --state-dir <connector_state> connect --setup-receipt <public_handoff> --alias m1-remote',
            '<NEXUS> connect --operator-profile m1-human --profile m1-remote --no-chat --timeout 120',
            '<CONNECTOR> --state-dir <connector_state> connect --identity m1-remote'
        ], 'Persisted root/children, one-shot host key only through existing protected prompt, human canonical approval, exact Finish receipt and binding; host never receives the operator credential.', 'New remote project identity/workspace/binding and reviewed host launch configuration, no auto project work.', 'Current root/map and canonical metadata match. All generated key material excluded from stdout/evidence/checkpoints.'),
        step('06-connector-work-decision-loss-recovery', [
            '<NEXUS> work send --operator-profile m1-human --profile m1-remote --request-id m1-remote-work-01 --message <finite_work.request> --json',
            '<NEXUS> work resume --operator-profile m1-human --profile m1-remote --json',
            '<NEXUS> work watch --operator-profile m1-human --profile m1-remote --timeout 120 --json',
            '<NEXUS> work answer --operator-profile m1-human --profile m1-remote --approval-id <actual_id> --json',
            '<NEXUS> work answer --operator-profile m1-human --profile m1-remote --approval-id <actual_id> --decision <reviewed_approve_or_deny> --review <actual_revision_hash> --json'
        ], 'Real HTTP/WebSocket/Core/provider path. One response-loss injection only after canonical submission admission and one after a decision ACK if technically controlled; then recover the saved same IDs without a second issue/decision. Retain uncertainty until a canonical receipt resolves it.', 'One useful request and reviewed permission; injected local client response loss is explicit instrumentation, not a claim of a naturally failing network.', 'Temporary client fault harness must be reviewed before execution and may only discard a known response. It must not log auth headers, touch provider transport, or mutate product binaries.'),
        step('07-connector-reconnect-and-result', [
            '<CONNECTOR> --state-dir <connector_state> connect --identity m1-remote',
            '<NEXUS> work status --operator-profile m1-human --profile m1-remote --json',
            '<NEXUS> work resume --operator-profile m1-human --profile m1-remote --json',
            '<NEXUS> work send --operator-profile m1-human --profile m1-remote --request-id m1-remote-work-02 --message <finite_work.continuation> --json'
        ], 'Completed setup reconnect preserves bootstrap/Finish/binding/config/IDs; reopened observer finds the same canonical result. Check productive operation cardinality, not only friendly output. At most one explicit continuation.', 'Read/reconnect, then optional explicit continuation within the finite allocation.', 'Do not force native process restart or claim resume without an exact supported grant; no hidden fresh session.'),
        step('08-close-drain-cleanup', [
            '<NEXUS> work close --profile m1-local --request-id m1-local-close --json <service-selection-args>',
            '<NEXUS> work close --operator-profile m1-human --profile m1-remote --request-id m1-remote-close --json',
            '<CONNECTOR> --state-dir <connector_state> daemon stop --timeout 60',
            '<NEXUS> service stop --home <server_home> --timeout 60 --json'
        ], 'Canonical close results, drain state, owned PID/birth exit, exact owned task disable/uninstall receipts under the separately reviewed service plan, final usage high-water per thread and no surviving owned process.', 'Only campaign sessions/services/tasks. Keep uncertain receipts for recovery; do not delete native personal history or authentication.', 'If BUSY/UNKNOWN, inspect and use an explicit already approved containment decision tied to the reviewed generation; never label timeout drained.'),
    ],
    'token_accounting': {
        'user_requested_total': 200000, 'unit': 'Aggregate native tokenUsage.total.totalTokens for this campaign, across both topologies and setup tests, including cached input as represented by the provider total.',
        'hard_cap_supported_by_current_flow': False,
        'blocker': 'Usage updates are observations after computation. Current TurnStartParams/harness settings expose no hard per-turn/output/aggregate token cap. Interrupt and force contain later, not at an atomically enforced token boundary. A finite number of turns and a large margin do not prove a strict 200000 ceiling.',
        'no_goal_workaround': 'Do not call thread/goal/set. It creates a persistent goal, is not the canonical work flow, and its tokenBudget has not been established as a campaign-wide hard cap.',
        'accounting_algorithm': [
            'Arm before any setup test. Replay committed canonical session events with native_type/native_event thread/tokenUsage/updated; validate complete contiguous cursors, namespace and stream_epoch.',
            'Keep one monotone high-water total.totalTokens per actual native thread. Map canonical stream epochs/sessions to that thread; resuming the same native thread must not count its cumulative total twice.',
            'Use fresh campaign threads. If an existing thread is ever reused, establish its pre-campaign high-water baseline first; otherwise accounting is UNKNOWN and no new work is submitted.',
            'Sum high-water deltas once across unique native threads; never add last and total or sum reasoning/cached subfields on top of totalTokens.',
            'Reject malformed, negative or regressing counters. Replay duplicates do not add usage. A gap, unavailable setup-test event stream, missing terminal usage or concurrent unknown native thread makes the total incomplete.',
            'On incomplete accounting: stop new admissions, request explicit canonical interrupt/close of the owned work, retain uncertainty and report known minimum only. Do not infer zero usage from absent events.',
        ],
        'operational_variant_not_yet_authorized': {
            'new_admission_stop_threshold': 100000,
            'interrupt_threshold': 120000,
            'serial_turn_deadline_seconds': 120,
            'meaning': 'A conservative operational plan only, not a guarantee that actual usage stays below 200000. Root must clarify whether this meets the user intent before any inference.',
        },
        'estimated_account_usage_endpoint': 'Not a substitute for campaign accounting; schema labels its thread usage estimated and the account may include unrelated activity.',
    },
    'fixed_plan_map': [
        {'requirement': 'M1 / DX-T39', 'proof': 'Steps02-04 local real terminal cycle; native service context additionally requires the approved platform lifecycle evidence.'},
        {'requirement': 'M1 / DX-T40', 'proof': 'Steps05-07 actual Connector execution and authenticated human operator; loopback process topology is not a second physical host.'},
        {'requirement': 'DX-T43', 'proof': 'Record service effective instructions/model/tools/limits and explicit provider context; unknown values stay unknown.'},
        {'requirement': 'DX-T45', 'proof': 'Actual native command permission/current actor/revision, never a model-authored permission sentence.'},
        {'requirement': 'DX-T46', 'proof': 'Controlled response loss + same-ID canonical recovery without repeated productive admission; if injection cannot be established, retain this case pending.'},
        {'requirement': 'DX-T47 / DX-T50', 'proof': 'Reopened CLI retrieves work and result without a dashboard; native context resumes only where supported.'},
    ],
    'blocking_preconditions_before_execution_request': [
        'Final SVC07 wheel/import/source hashes and installed platform dependencies must be pinned.',
        'Clarify the requested token ceiling: a strict aggregate hard cap is not guaranteed by current interfaces.',
        'Pin the native authentication context and authorize only its native use; current prepared artifact has no login configured or inspected.',
        'Pin exact service homes/task names/argv/port and verify target ownership/absence immediately before requesting service effects; no broad user service authorization is inferred.',
        'Confirm the canonical effective policy can produce the qualified permission method without manual personal config edits; otherwise that native-decision gate remains pending.',
        'Implement/review the finite usage collector and response-loss harness against installed canonical event shapes before running a paid campaign; they are not supplied as completed runtime tooling in this proposal.',
    ],
    'excluded': ['Personal file discovery', 'Reading/copying authentication files', 'Replacing/updating the personal Codex installation', 'Unqualified0.167 capability promotion', 'Persistent Codex goals', 'Background autonomous turns', 'Agent spawning', 'Unreviewed model/tool/sandbox changes', 'Remote administrator credential on Connector', 'Reboot/logout', 'Force closing any unowned process', 'Deleting personal provider history', 'M2/global acceptance from this preparation'],
    'evidence_policy': {'public_allowlist': ['JSON metadata/hashes/counters/status/IDs', 'reviewed nonsecret command templates', 'sanitized event metadata and operation cardinalities', 'synthetic fixture hashes'], 'private_only': ['raw local outputs until curated', 'operator/host checkpoint material when sensitive'], 'never_collect': ['auth headers', 'API keys', 'operator cookies', 'provider auth/config files', 'personal native transcripts'], 'never_commit': ['downloaded executables/ZIPs', 'homes/databases/vaults']},
    'references': [
        {'url': 'https://github.com/openai/codex/releases/tag/rust-v0.157.0', 'basis': 'Official release page opened during this preparation; exact asset obtained from official GitHub release metadata.'},
        {'url': 'https://learn.chatgpt.com/docs/app-server', 'basis': 'Official documentation context supplied by root; local pinned schema independently confirms token usage and persistent goal fields. No hard-cap assertion is derived from that page.'},
    ],
    'read_source_snapshots': snapshots,
    'acceptance': 'No M1 status promotion. Preparation-only; binary bytes and pure compatibility predicate checked, no native provider or service campaign executed.',
}
with (PUBLIC / 'm1-codex-campaign-proposal.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(proposal, ensure_ascii=False, indent=2) + '\n')

md = r'''# Proposta M1 Codex CLI — preparada, não autorizada nem executada

A campanha proposta é finita: um ciclo local e outro executado pelo Connector, ambos pelo terminal e com decisão nativa real. Nenhuma inferência, leitura de credencial, processo nativo ou serviço foi iniciado nesta preparação. A informação de que a conta já está autenticada e o limite total de 200 mil tokens orientam esta proposta; não autorizam a execução.

## Artefato concreto disponível

O [release oficial0.157.0](https://github.com/openai/codex/releases/tag/rust-v0.157.0) foi baixado exclusivamente neste Temp. O ZIP tem SHA256 `6c74e2019583cc16e55f79161ef795c8ff712709ad9ed832b3a5b87a7eacdef6`. O executável interno tem322525488bytes e SHA256 `ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f`, igual ao build qualificado no Core. As funções puras atuais confirmaram conversa e controles; o único pedido nativo qualificado desse build é `item/commandExecution/requestApproval`. Nenhum executável, helper de sandbox ou postinstall foi rodado.

A igualdade é pelo fingerprint de conteúdo do executável. O `build_identity.v3` calculado (`0bf80fe3…26535`) não coincide com o grant portátil histórico (`df63d86e…edcb`). Não foi alterada allowlist: o ramo atual de `qualified_build` aceita o fingerprint exato, e `discovery.fingerprint()` realmente retorna o SHA bruto. A aprovação canônica do novo caminho/projeto continua necessária. Os dois comprovantes JSON preservam separadamente a tentativa inicial de comparar apenas a identidade portátil e a verificação correta pela API pura.

O0.167.0 pessoal permanece intacto e não recebe capacidade por inferência. O0.159.0 estável não basta para a decisão representativa: só tem os controles qualificados. O alpha0.159.0-alpha.12.1 tem `requestUserInput` qualificado, mas não foi escolhido nem baixado.

## Etapas e efeitos revisáveis

1. Pinar wheels instaladas finais do SVC07, imports, ambiente, dois projetos descartáveis e os alvos de serviço por usuário. Os hashes finais ainda estão pendentes; a proposta anterior de serviço é referência histórica, não autorização nem fonte de hashes atuais.
2. Fazer `connect --plan` local, rever candidato físico, identidade, workspace, preset e contexto efetivo. Aprovar só a revisão exibida e usar `--no-chat`. O teste de conexão local já pede resposta ao modelo e entra na conta de tokens.
3. Pedir um trabalho pequeno: ler `numbers.csv` contendo1,2,3,4 e apresentar contagem4, soma10 e SHA256. Observar uma permissão nativa real. Aprovar somente comando exato de leitura/cálculo nesse projeto; se o pedido divergir, negar/parar. Texto do modelo não comprova uma permissão. Se a política efetiva não produzir o método qualificado, o caso fica pendente, sem turnos extras para forçá-lo.
4. Fechar e reabrir o cliente de terminal, recuperar mesmos IDs e resultado, e realizar no máximo uma continuação curta explicitamente solicitada. Sair do cliente não interrompe trabalho. Retomar contexto nativo após perda do processo só se o contrato específico comprovar suporte; nenhuma sessão nova disfarçada de retomada.
5. No host Connector, exportar o rascunho não secreto com `--setup-draft`; o operador humano usa `OperatorProfile`, revisão persistida e Finish existentes. A chave do agente passa apenas pelo mecanismo protegido existente; cookie/chave de administrador não vai ao host. A conexão concluída é retomada sem repetir probe, Finish ou concessões.
6. Repetir o trabalho e a decisão pelo caminho real HTTP/WebSocket/Connector/Core. Aplicar uma perda controlada de resposta depois da admissão canônica e, se houver controle técnico demonstrável, uma depois do ACK da decisão. Recuperar checkpoint/IDs anteriores; nunca emitir novamente com ID novo para sanar incerteza. A falha de rede é injeção declarada em cliente temporário, não falha natural nem mock do provider.
7. Reabrir o cliente, conferir resultado e cardinalidade dos efeitos, e fazer no máximo uma continuação explícita. Fechar sessões canonicamente, drenar serviços, verificar saída dos PIDs/births possuídos e desinstalar só os alvos temporários previamente aprovados.

O JSON contém os comandos e gates por etapa. São templates revisados pelo parser, não comandos executados. Valores gerados em revisão (`candidate_ref`, revisions, IDs) não são inventados. O máximo proposto é6admissões produtivas, contando eventuais testes de conexão; execução serial, sem retry automático de turnos e sem subagentes. Isso limita o roteiro, não garante um limite de tokens por turno.

## Teto de tokens: impedimento explícito

O contrato atual **não comprova um teto rígido agregado de200000tokens**. `TurnStartParams` não contém limite de saída/tokens; as configurações portáveis também não. `thread/tokenUsage/updated` chega depois de computação, e `interrupt`/contenção não são uma transação atômica com a contagem de tokens. Nem um roteiro curto nem uma margem grande eliminam a possibilidade de ultrapassagem.

A [documentação do app-server](https://learn.chatgpt.com/docs/app-server), consultada pelo root, e o schema local descrevem uso por thread e `thread/goal/set`. Este último cria estado persistente e não foi comprovado como hard cap da campanha; não será usado como atalho.

Se o usuário aceitar um limite **operacional**, a proposta é não admitir novo trabalho após100000tokens observados e solicitar interrupção após120000ou120s de um turno, mantendo margem ao valor solicitado. Ainda pode haver overshoot; essa interpretação exige esclarecimento antes de qualquer inferência. Se200000for limite rígido, a campanha fica bloqueada até existir uma garantia efetiva aplicável ao fluxo, sem substituir o requisito por promessa.

A contagem deve estar armada antes do primeiro teste de conexão. Por thread nativa, manter high-water de `tokenUsage.total.totalTokens` e somar só deltas, sem duplicar notificações, `last`/`total` ou parcelas de cache/raciocínio. Mapear stream epochs ao mesmo thread; retomada do mesmo thread não reinicia contagem. Ausência/gap/regressão ou falta de eventos do teste de conexão significa total incompleto: impedir novas admissões, interromper/fechar somente o trabalho possuído e reportar mínimo conhecido. O coletor e a injeção de resposta ainda precisam ser implementados e revistos contra a wheel final; não são alegados como instrumentação pronta.

## Contexto e limites que continuam abertos

- A execução nativa pode ler a autenticação/configuração de seu `provider_home` e escrever seu próprio histórico ou refresh. Executável e workspace em Temp não isolam automaticamente o login. O agente não leu, copiará ou divulgará esses arquivos; o contexto exato e seu uso nativo precisam de autorização explícita.
- O modelo, instruções, tools, sandbox, approval policy e MCPs efetivos devem vir do fluxo canônico. Não foi presumido que o serviço herdou o shell, nem que o preset altera esses valores. Alterar configuração pessoal manualmente não é saída para fechar o percurso padrão.
- O Connector proposto usa processos/homes separados em loopback: prova a topologia de execução remota por protocolo, não rede entre duas máquinas físicas. Não promove M2 nem campanhas multiplataforma.
- O caso de permissão usa somente o método previamente qualificado. Não amplia suporte de input, fileChange, elicitation ou0.167.0. Não modifica projetos pessoais, não instala dependências por instrução do modelo e não concede autorização ampla de comandos.
- Publicação só de metadados, hashes, contagens, IDs e estados sanitizados. ZIP/executáveis, homes, bancos, auth, cookies e respostas brutas potencialmente sensíveis ficam fora da curadoria pública.

Mapeamento do plano: M1/DX-T39local; M1/DX-T40Connector; DX-T43contexto efetivo; DX-T45decisão nativa; DX-T46perda/recuperação sem duplicação; DX-T47retorno do terminal; DX-T50sem dashboard obrigatório. Nenhum desses aceites foi promovido por esta preparação.
'''
with (PUBLIC / 'm1-codex-campaign-proposal.md').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(md)
print(json.dumps({'proposal': str(PUBLIC / 'm1-codex-campaign-proposal.json'), 'read_source_files': len(snapshots), 'native_executions': 0}))
