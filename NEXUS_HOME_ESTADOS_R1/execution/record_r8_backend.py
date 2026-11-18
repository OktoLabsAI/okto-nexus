"""Record six actual R8 installed cases, not the failed seventh or real providers."""
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
relative = 'remaining-qualification-r7-next/backend-batch/attempt5-r8/qualification.json'
q = json.loads((HERE / relative).read_text())
assert (q['passed'], q['failed'], q['not_run']) == (6, 1, 0)
assert q['physical_same_birth_remaining'] == 0 and not q['timeout_or_force_used']
assert q['payload_files'] == 1031 and all(not value for value in q['guards'].values())
assert all(node['status'] == 'PASS' for node in q['nodes'][:6])
assert q['nodes'][6]['status'] == 'FAIL'
qualified = [scenario for node in q['nodes'][:6] for scenario in node['scenario_proposal']]
assert qualified == ['A04', 'B12', 'A06', 'B08', 'C01', 'C05', 'C06']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
for test in ledger['tests']:
    if test['id'].removeprefix('HST-T-') not in qualified:
        continue
    node = next(node for node in q['nodes'][:6] if test['id'].removeprefix('HST-T-') in node['scenario_proposal'])
    assert [phase['outcome'] for phase in node['phases']] == ['passed'] * 3
    entry = {'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
        'artifact_path': 'execution/' + relative,
        'environment': 'Actual installed R8 Nexus/Core/Connector from immutable prefix; copied tests and canonical Core with inert JSON-RPC peer, no real provider',
        'command_or_procedure': node['node'],
        'result': 'PASS literal installed HTTP/SQLite criterion; actual started/progress/input and scoped admissions; setup/call/teardown all passed; source/payload/copy/helper/tooling drift0',
        'limitations': 'No browser or provider claim. A04 shared-work correlation is explicitly historical SQL metadata; live authority/progress is canonical. C06 is unknown-dependent queue, not C07 independent-queue proof. Six-table snapshots do not prove whole-DB passivity. Only two raw cleanup JSONs survived pytest retention; six teardown close assertions passed, no missing snapshots fabricated.'}
    test['status'] = 'PASS'
    if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
        test['evidence'].append(entry)
    test['execution_notes'] = 'Actual R8 installed qualification: ' + node['node'] + '. Per-layer/history/retention limits remain in the evidence.'
ledger['execution']['r8_backend_batch'] = {'evidence': 'execution/' + relative,
    'executed_on_r8': True, 'counts': {'PASS': 6, 'FAIL': 1, 'NOT_RUN': 0},
    'qualified_scenarios': ['HST-T-' + scenario for scenario in qualified],
    'failure': q['failure'], 'E16': 'NOT_QUALIFIED; wrong source-copy presentation title stopped before Seen/noACK assertions',
    'source_and_payload_drift': [], 'physical_same_birth_remaining': 0,
    'real_provider': False, 'whole_batch_green': False,
    'raw_retention_limit': q['raw_retention_limit']}
ledger['execution']['r8_package']['subsequent_installed_backend_tests'] = 'Six targeted cases actually passed on R8; seventh presentation oracle failed. Package-time pytest=false remains historical.'
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'qualified': qualified, 'counts': ledger['execution']['r8_backend_batch']['counts']}))
