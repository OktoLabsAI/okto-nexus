"""Apply the user's local performance policy without rewriting measurements."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
dom = json.loads((HERE / 'performance-hst/large-dom-r7-final/qualification.json').read_text())
assert dom['samples'] == 1 and not dom['is_p95'] and dom['functional_oracle'] == 'PASS'
assert dom['target_ms'] == 2000 and dom['first_useful_dom_ms'] > dom['target_ms']
assert dom['cleanup']['normal_http_exit'] and dom['cleanup']['normal_cli_close']
assert not dom['cleanup']['owned_remaining'] and not dom['cleanup']['listeners']
stamp = datetime.now(UTC).isoformat()
entry = dict(commit=dom['source_commit'], timestamp=stamp,
    artifact_path='execution/performance-hst/shared-machine-interpretation.md',
    command_or_procedure='Apply user clarification after retaining raw matrix, three-GET profile and actual useful-DOM observation',
    environment='Shared Windows machine; unrelated concurrent processes/load not controlled; only own readers sequenced',
    result='DIAGNOSTIC_NON_BLOCKING_FOR_LOCAL_ACCEPTANCE per user; raw threshold misses remain unchanged',
    limitations='No numerical pass, causal-regression proof, production qualification or default approval. No further performance-only tuning/measurement round. Functional omissions and previous gates remain separate.')
for task in ledger['tasks']:
    if task['id'] in ('HST-027', 'HST-032'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
    if task['id'] == 'HST-027':
        task['status'] = 'IMPLEMENTED'
        task['execution_notes'] = 'Measurements/diagnosis/report complete in this shared environment; timings diagnostic/non-blocking per user. Not controlled production-performance verification.'
for test in ledger['tests']:
    if test['id'] in ('HST-T-J04', 'HST-T-J05'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
    if test['id'] == 'HST-T-J04':
        test['status'] = 'NOT_RUN'
        test['execution_notes'] = 'PARTIAL functional J04 criterion: actual1000OPEN/100000history, query counts and paginated response sizes were observed. A dedicated assertion covering transcript/native-payload materialization and adversarial large-output bounds across these endpoints is still missing. Latency is not this Then criterion and is not its failure reason; prior timing-based annotation remains historical evidence.'
ledger['execution']['performance_interpretation'] = dict(
    user_instruction='nao leve tao a serio essas medicoes de performance pois temos outros processos rodando na mesma maquina que podem impactar essa medicao',
    policy='DIAGNOSTIC_NON_BLOCKING_FOR_THIS_LOCAL_ACCEPTANCE',
    environment='SHARED_MACHINE_EXTERNAL_LOAD_UNCONTROLLED',
    measured_targets_unchanged=True, historical_cuts_unchanged=True,
    numerical_pass_inferred=False, causal_regression_inferred=False,
    further_performance_only_work='DEPRIORITIZED_PER_USER',
    interpretation=entry['artifact_path'], timestamp=stamp)
ledger['execution']['large_dom_r7'] = dict(
    artifact='execution/performance-hst/large-dom-r7-final/qualification.json',
    samples=dom['samples'], is_p95=False,
    first_useful_dom_ms=dom['first_useful_dom_ms'], reference_target_ms=dom['target_ms'],
    raw_observation_status=dom['status'], functional_oracle='PASS',
    policy='DIAGNOSTIC_NON_BLOCKING_SHARED_MACHINE', provider_calls=0,
    own_cleanup='normal0/physical0; no force/timeout/drift')
ledger['execution']['performance_r7'].update(
    current_policy='DIAGNOSTIC_NON_BLOCKING_SHARED_MACHINE_PER_USER',
    correction_status='DEFERRED_DIAGNOSTIC_OPTION',
    first_useful_dom='MEASURED_N1_2725.6MS; shared-machine diagnostic')
ledger['execution']['performance_r7'].pop('human_readiness', None)
ledger['execution']['performance_r7']['human_readiness_basis'] = 'Not inferred from diagnostic timing; see functional review and human_evaluation separately.'
ledger['execution']['r7_source']['performance'] = 'DIAGNOSTIC_NON_BLOCKING_SHARED_MACHINE_PER_USER; raw target misses retained'
ledger['execution']['r7_validation'].update(
    performance='DIAGNOSTIC_NON_BLOCKING_SHARED_MACHINE_PER_USER; raw misses retained',
    first_useful_dom='MEASURED_N1_2725.6MS; functional correspondence PASS, timing diagnostic')
ledger['execution']['observed_scenario_reconciliation']['performance'] = 'MEASURED_DIAGNOSTIC_NON_BLOCKING_PER_USER'
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(performance_policy=ledger['execution']['performance_interpretation']['policy'],
    measured_dom_ms=dom['first_useful_dom_ms'], default_rollout=ledger['execution']['default_rollout_approved'])))
