"""Record the closed PR10b scope while preserving every remaining R3 gate."""
import json
from pathlib import Path

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
EVIDENCE = 'plans/agent_ops/evidence/pr10-correlation'
reports = json.loads((REPO / EVIDENCE / 'reports.json').read_text(encoding='utf-8'))
assert reports['collection_phase'] == 'closed_qualified_milestone'
assert reports['installed_qualification']['qualified_union'] == 756
benchmark = reports['benchmark_candidate_v2']
assert benchmark['samples'] == 90
passed = benchmark['passed']
refused = benchmark['attention_budget_refusals']
ledger_path = REPO / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
assert ledger['plan_sha256'] == '20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
assert ledger['tasks']['OBS-12']['status'] == 'IN_PROGRESS'
assert ledger['scenarios']['OB-19']['status'] == 'NOT_RUN'
assert ledger['milestones']['PR-10']['status'] == 'IN_PROGRESS'
evidence = [EVIDENCE + suffix for suffix in ('.md', '/reports.json',
    '/candidate-v2/package-proof.json', '/candidate-v2/package-delta.json',
    '/candidate-v2/installed.xml', '/browser/campaign-summary.json',
    '/benchmark/candidate-v1/assessment.json', '/benchmark/candidate-v2/assessment.json',
    '/artifact-manifest.json')]
result = (
    'Explicit operator correlation is installed-qualified with bounded CAS/tombstone storage, '
    'existing-runtime Core birth reading, host-owned Windows identity comparison and current '
    'authority revalidation, operator-only HTTP management, passive canonical batch projection '
    'and canonical-first UI. Historical completion does not inherit later correlation; '
    'external activity/summary remain separate and receipt metadata does not imply liveness. '
    'Candidate V1 passed 736 distinct installed cases. V2 changes only two attention SQL modules '
    'and passed 237 affected installed cases (217 repeats and 20 new), yielding 756 distinct '
    'identities across candidates, including 519 unchanged V1 cases not rerun on V2. '
    'All 681 final source/build/wheel/installed package files match; 679 files, all seven static '
    'assets and Core are unchanged from V1. Frontend has 130 passes. Actual browser/HTTP on V1 '
    'passed eight synthetic-data checkpoints with 13 canonical tables unchanged and complete '
    'cleanup. Initial load measurement retained 86 successful samples and four five-second '
    'budget refusals. Exact current-head selection removes unnecessary working-head correlation '
    f'preload; the same frozen 90-sample follow-up has {passed} successful samples and {refused} '
    'budget refusals, without retries or deadline changes. OBS-12 and OB-19 are verified for '
    'the declared Windows/local contract. Real process/Core association, providers, clients, '
    'native services, joint PR-10 and full R3 acceptance remain open.'
)
task = ledger['tasks']['OBS-12']
task['status'] = 'VERIFIED'
task['result'] = result
task['platform'] = 'Windows-11-10.0.26300-SP0'
task['tests'] = sorted(set(task['tests'] + evidence))
task['files'] = sorted(set(task['files'] + [
    'src/okto_nexus/adapters/inbound/http/observations.py',
    'src/okto_nexus/adapters/outbound/sqlite/attention.py',
    'src/okto_nexus/adapters/outbound/sqlite/attention_external.py',
    'src/okto_nexus/adapters/outbound/sqlite/observation_correlation_facts.py',
    'src/okto_nexus/application/observation_correlation_ports.py',
    'tests/test_attention_correlation_policy.py',
    'tests/test_observation_correlation_http.py',
    'tests/test_observation_correlation_proof.py',
    'tests/test_observation_correlation_projection.py',
    'tests/test_observation_correlation_view.py',
    'tests/test_observation_correlations_storage.py',
    'tests/test_observation_process_birth.py',
]))
task['limitations'] = [
    'Native association is initially local Windows/embedded. Synthetic Core/process data qualify boundaries and precedence, not an actual live process association campaign. Remote or insufficiently matched observations remain separate.',
    'The five-second proof budget is an admission deadline, not a hard bound on OS calls or SQLite commit. Batch 32 MiB accounting covers fetched UTF-8 text including JSON, not DTO serialization, Python RSS or SQLite sort memory. Tombstones consume bounded capacity and are not automatically pruned.',
    'V1 browser evidence is retained as V1; V2 changes only two attention SQL modules and requalifies affected reads. Measurements cover 1/64 sessions with 64/512/4096 correlated instances, half blocked/half working, not 4096 distinct sessions or a general latency SLO.',
    'Real providers, native service lifecycle, qualified external clients, M1/M2, joint rollout/regression and full R3 remain open.',
]
task['subscopes'].update(authorized_mapping_and_native_proof='VERIFIED',
    canonical_precedence_projection='VERIFIED', installed_correlation_qualification='VERIFIED')
ledger['scenarios']['OB-19'].update(status='VERIFIED', evidence=evidence)
ledger['milestones']['PR-10']['evidence'] = sorted(set(ledger['milestones']['PR-10']['evidence'] + evidence))

diagnostic_result = (
    '\n\nShared diagnostic v1 is now installed-qualified on both hosts: Nexus 75 distinct cases '
    'and Connector 93 distinct cases, each matching its source suite rather than adding to it. '
    'The four common fixture files are byte-identical with contract digest '
    '06dbbea77eb0870058bc2fe4c9afc81023ea99f857612984321d1f8e6d20c422. '
    'Legacy default/exits remain unchanged; v1 projects the existing typed observation without '
    'extra probes, provider calls, credential reads or authority. Nexus diagnostics bytes are '
    'unchanged between OBS12 V1 and final V2. This verifies the common declarative contract, '
    'not a real two-host campaign. The broader task and real provider/client/service gates remain open.'
)
for name in ('DX-07', 'DX-14'):
    item = ledger['tasks'][name]
    assert item['status'] == 'IN_PROGRESS'
    item['subscopes']['nexus_shared_diagnostics_v1_installed'] = 'VERIFIED'
    item['result'] += diagnostic_result
    item['tests'] = sorted(set(item['tests'] + [
        'plans/agent_ops/evidence/pr10-diagnostics-nexus.md',
        'plans/agent_ops/evidence/pr10-diagnostics-connector.md',
        EVIDENCE + '/diagnostics/shared-contract-comparison.json',
        EVIDENCE + '/installed/diagnostics/installed.xml',
    ]))
ledger['tasks']['DX-07']['subscopes']['cross_host_diagnostic_contract'] = 'VERIFIED'
ledger['history'].append(dict(date='2026-11-07', milestone='PR-10', status='IN_PROGRESS',
    summary=result + ' Shared diagnostics declarative contract is also verified; broader DX-07/DX-14 remain IN_PROGRESS.',
    evidence=evidence + ['plans/agent_ops/evidence/pr10-diagnostics-nexus.md']))
ledger['updated_at'] = '2026-11-07'
ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

root_ledger = REPO / 'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
with root_ledger.open('a', encoding='utf-8') as stream:
    stream.write(f'''

## 2026-11-07 — PR-10b: precedência canônica e diagnóstico comum qualificados

OBS-12 e OB-19 passam a VERIFIED no escopo Windows/local declarado. Associação explícita de operador, CAS/tombstones, revisão de autoridade e projeção passiva preservam os fatos canônicos e mantêm o sinal externo separado. A prova de processo/Core desta fatia usa dados sintéticos; isso não qualifica associação real com provedor.

A V1 passou em 736 casos instalados. A V2 altera somente duas consultas de atenção e passou nos 237 casos afetados, com 20 identidades novas: são 756 casos distintos entre candidatos, dos quais 519 permanecem qualificados na V1 inalterada. Os 681 arquivos finais correspondem ao fonte/build/wheel/instalação; 679 arquivos e os sete assets são idênticos à V1. Frontend: 130 passes. Browser real V1: oito checkpoints, 13 tabelas canônicas preservadas e encerramento confirmado.

A medição inicial preserva 86/90 sucessos e quatro recusas pelo orçamento de cinco segundos. Após restringir o preload às ocorrências pertinentes, o mesmo driver registrou {passed}/90 sucessos e {refused} recusas na V2, sem retries nem alteração do prazo. Resultados são separados por candidato; não constituem SLO geral. [Evidências, falhas iniciais e limites](plans/agent_ops/evidence/pr10-correlation.md).

Diagnóstico comum v1 verificado: Nexus 75 casos instalados; Connector 93 já publicados em `12d806f955aea84327dd3a33011016d0283ecc18`. São os mesmos casos fonte de cada repo, sem soma duplicada. O contrato compartilhado é declarativo; DX-07/DX-14 completos e campanhas reais entre hosts continuam em andamento. Core permanece sem alterações neste milestone.

PR-10 integral e R3 continuam IN_PROGRESS. Bootstrap remoto, M1/M2 produtivos, campanhas de serviço/provedor/cliente e regressão conjunta permanecem abertos. Plano e inventários fixos preservados.
''')

report = REPO / 'plans/agent_ops/implementation-report.md'
with report.open('a', encoding='utf-8') as stream:
    stream.write(f'''

## PR-10a / PR-10b — external observations, canonical precedence and diagnostics

OBS-11 exposes three external watch kinds, exact inspection and complete summaries; its previously published qualification is recorded in [PR-10a](evidence/pr10-external.md). OBS-12 now adds explicit operator-only association, bounded CAS/tombstones, existing-runtime process-birth inspection and canonical-first passive metadata. Canonical receipt/session facts never become an external activity report or execution authority; historical completions remain independent of later association. Additive migration 166 stores only the explicit association and fences. Remote or insufficiently matched observations remain separate.

Nexus 0.3.3 final wheel is `{reports['wheel_sha256']}`. All 681 source/build/wheel/installed files match. V1 passed 736 distinct installed cases; V2 passed 237 affected cases after changing two attention modules. Their union is 756 identities, including 519 unchanged V1 cases not rerun on V2. Frontend passed 130 cases and built with TypeScript/Vite. Actual Chrome/HTTP V1 passed eight synthetic-data checkpoints, preserving 13 canonical tables; all seven static files remain byte-identical in V2. Source, installed and frontend counts are separate. Forty changed Python files pass Ruff.

The first fixed load campaign retained 86 successes and four five-second budget refusals. Reusing the exact current-head predicate avoids loading correlations for working heads that cannot appear in attention. The byte-identical driver measured {passed} successes and {refused} budget refusals in 90 V2 samples, with no retries or deadline relaxation. Both campaigns retain original reports, failures and canonical-fingerprint/read-only trace checks. This is a measurement of 1/64 sessions and up to 4096 correlated instances, not a general latency SLO.

The same milestone qualifies optional shared diagnostic v1 on Nexus (75 installed cases) and the already published Connector 0.0.12 commit `12d806f955aea84327dd3a33011016d0283ecc18` (93 installed cases). Four fixture files have the same contract digest. Legacy output and exits remain default; typed observation is projected once without new probes or authority. Core 0.0.14 remains unchanged. Test commands and exact installed import guards are retained with the [evidence](evidence/pr10-correlation.md) and [diagnostics report](evidence/pr10-diagnostics-nexus.md).

Compatibility remains additive: absent or invalid associations project null, disabled sources/revoked keys preserve fences, and no association changes canonical execution state. Disable or clear the association through the authorized API to stop projection. Migration 166 is not destructively reversed; retain the database and take a supported backup before any binary rollback. Tombstones consume finite capacity. The five-second proof budget bounds admission, not blocking OS/COMMIT duration; the 32 MiB read budget counts fetched UTF-8 text rather than process RSS.

OBS-12 and OB-19 are VERIFIED in the declared Windows/local contract. PR-10, broader DX-07/DX-14 and full R3 remain IN_PROGRESS. Real OS/Core association, providers, external-client cooperation, native-service lifecycle and productive M1/M2 are not certified by synthetic fixtures. The next implementation dependency is the remote identity/setup path, followed by the still-pending joint and authorized real campaigns. The fixed 59 tasks, 132 scenarios, 28 invariants, 17 criteria and plan hash are preserved.
''')
print(json.dumps(dict(obs12=task['status'], ob19=ledger['scenarios']['OB-19']['status'],
    pr10=ledger['milestones']['PR-10']['status'], full_r3=ledger['status']), indent=2))
