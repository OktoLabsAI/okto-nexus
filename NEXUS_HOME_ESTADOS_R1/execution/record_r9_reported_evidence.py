"""Qualify reported completion while retaining narrower capacity limits."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/security-r9-s2-batch/runs/hst-security-r9-s2-observed-completion-v3'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, digest in read(cut / 'manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == digest, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_SCOPED' and q['case'] == 'S2'
assert q['provider_invocations'] == 0 and q['missing_phases'] == []
assert sum(len(phase['checks']) for phase in q['results']) == 13
assert all(check['ok'] for phase in q['results'] for check in phase['checks'])
assert len(q['drift']) == 2 and len(q['table_snapshots']['before']['tables']) == 30
for window in q['drift']:
    assert not any(window[key] for key in ('changes', 'expected_observation_errors', 'ignored_tables', 'ignored_columns'))
assert [row['sequence'] for row in q['drift'][1]['allowed_observation_events']] == [1, 2]
assert [row['type'] for row in q['drift'][1]['allowed_observation_events']] == ['observation.activity', 'observation.completion']
assert all(row['observational_only'] for row in q['drift'][1]['allowed_observation_events'])
assert q['guards']['equal'] and q['cleanup']['normal'] and q['cleanup']['physical_absence']
assert not q['cleanup']['forced'] and not q['cleanup']['listeners']
closes = q['cleanup']['runtime_close_observations']
assert not closes['close_failures'] and all(row['closed'] for row in closes['sessions'])
assert not q['raw_auth_copied'] and not q['private_rows_copied']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Fresh installed R9, actual own-profile Chrome, canonical source/instance/token and observation publication APIs, canonical Core with inert native peer; no provider',
    'command_or_procedure': 'Publish sequence1 idle and sequence2 external completion once each; inspect actual board and exact canonical-attention completion episode; compare thirty productive tables across both live publication/read windows',
    'result': 'PASS13 browser predicates: unlinked idle creates no native session/result, exactly one reported delivery with unknown native outcome/verification, explicit Not verified by Nexus, exact source/instance/workspace/generation/sequence2 reference opens; GET-only; two table comparisons permit only the exact scoped observational events and no other changes; guards0drift, normal0/physical0, both canonical session closes confirmed',
    'limitations': 'No occupied claim or one-shot slot in this baseline, so H08 capacity-release clause is not qualified. Earlier JSON parsing failure and wrong-modal oracle cut remain unchanged. Reader audit observed two missing-control-file reads and zero invalid JSON; it does not prove the first failure cause. No native success/task completion/verification or real provider claim.'}
for test in ledger['tests']:
    if test['id'] in ('HST-T-E13', 'HST-T-H08') and not any(
        old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']
    ):
        test['evidence'].append(entry)
    if test['id'] == 'HST-T-E13':
        test['status'] = 'PASS'
        test['execution_notes'] = 'Actual canonical reported-completion API/SQLite plus installed browser qualifies explicit reported evidence, no native success/verification, and exact external-completion detail.'
    if test['id'] == 'HST-T-H08':
        test['execution_notes'] = 'PARTIAL: only two exact observational events change across thirty tables; runtime/grant/handoff rows stay identical. No occupied claim/one-shot slot exists in this baseline, so capacity release under active work remains unexecuted.'
ledger['execution']['r9_security_s2'] = {
    'status': 'PASS_SCOPED_E13', 'qualification': entry['artifact_path'],
    'browser_checks': 13, 'live_table_windows': 2, 'tables_per_window': 30,
    'allowed_event_sequences': [1, 2], 'provider_calls': 0,
    'canonical_session_closes': 'BOTH_CONFIRMED', 'normal_exit': True,
    'physical_absence': True, 'H08_occupied_capacity': 'NOT_RUN'}
pending = ledger['execution']['local_usability_candidate']['pending_local_scopes']
pending[:] = [item for item in pending if item != 'external observation browser security']
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'E13': 'PASS', 'H08': 'PARTIAL', 'real_provider_calls': 0}))
