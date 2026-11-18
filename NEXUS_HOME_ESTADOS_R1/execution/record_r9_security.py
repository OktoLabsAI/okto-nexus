"""Record the executed passive-read window and scoped canonical revocation."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/security-r9-batch/runs/hst-security-r9-s1-comment-only'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, expected in read(cut / 'final-manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == expected, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_SCOPED' and q['case'] == 'S1'
assert q['source_commit'] == 'f07163ab7fd618b2ff4247ba6cdb2547b5d4e038'
assert q['provider_invocations'] == 0 and q['missing_phases'] == []
assert sum(len(phase['checks']) for phase in q['results']) == 20
assert all(check['ok'] for phase in q['results'] for check in phase['checks'])
assert len(q['table_snapshots']['before']['tables']) == 30
assert len(q['drift']) == 1
window = q['drift'][0]
assert window['before'] == 'before-get' and window['after'] == 'after-get'
assert not any(window[key] for key in ('changes', 'ignored_tables', 'ignored_columns'))
assert q['guards']['equal'] and q['cleanup']['normal'] and q['cleanup']['physical_absence']
assert not q['cleanup']['forced'] and q['cleanup']['fixture']['exit_code'] == 0
assert not q['cleanup']['listeners'] and not q['raw_auth_copied']
close = q['cleanup']['runtime_close_observations']
assert close['close_failures'] and not close['all_runtime_close_receipts_claimed']
assert not close['revoked_authority_renewed']
assert q['actual_own_browser_before_home']['status'] == 'EXACT_OWN_PROFILE_MAIN_CAPTURED'
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Fresh installed R9; actual own-profile Chrome over owned HTTP fixture and canonical Core with inert protocol peer; provider PATH empty',
    'command_or_procedure': 'Snapshot thirty productive tables immediately before and after actual Home/card/result reads; independently revoke exact grant through canonical DELETE and inspect exact session controls before/after',
    'result': 'PASS20 focal browser checks; paired thirty-table read window has identical row/hash snapshots without ignored tables/columns; GET-only and no page errors; exact revoked session remains readable while its controls disappear; source1829/payload1031 drift0 and normal owner/browser exit with physical absence',
    'limitations': 'No forged URL, hostile DOM, wrong-recipient decision, uncertain retry or same-name successor browser qualification. Auth telemetry is outside thirty productive tables. After canonical revocation, last runtime.close was refused and closed=false is preserved; normal lifespan exit is not a successful close receipt. Inert protocol peer is not a real harness.'}
for test in ledger['tests']:
    if test['id'] in ('HST-T-H01', 'HST-T-H07', 'HST-T-H09') and not any(
        old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']
    ):
        test['evidence'].append(entry)
    if test['id'] == 'HST-T-H01':
        test['status'] = 'PASS'
        test['execution_notes'] = 'Actual browser/API reads and paired thirty productive table snapshots qualify passive Home/card/result inspection; auth metadata explicitly separate.'
    if test['id'] == 'HST-T-H07':
        test['execution_notes'] = 'PARTIAL: canonical DELETE revokes exact session lease, same full tuple is retained and UI removes controls. Stale decision submission and same-name successor browser clauses remain unexecuted.'
    if test['id'] == 'HST-T-H09':
        test['execution_notes'] = 'PARTIAL: API and real card do not invent individual reconnect when unavailable; the full adversarial detail/daemon-restart limitation clause remains unexecuted.'
ledger['execution']['r9_security_s1'] = {
    'status': 'PASS_SCOPED_H01_AND_REVOCATION_SUBSET', 'source': q['source_commit'],
    'qualification': entry['artifact_path'], 'browser_checks': 20,
    'passive_tables': 30, 'ignored_tables': [], 'provider_calls': 0,
    'canonical_runtime_close': 'LAST_CLOSE_REFUSED_AFTER_REVOKE; CLOSED_FALSE_RETAINED',
    'normal_owner_exit': True, 'physical_absence': True,
    'other_security_scenarios_promoted': False}
pending = ledger['execution']['local_usability_candidate']['pending_local_scopes']
pending[:] = ['external observation browser security' if item == 'passive/revocation/observation browser security' else item for item in pending]
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'H01': 'PASS', 'H07': 'PARTIAL', 'H09': 'PARTIAL', 'human': 'NOT_INVITED'}))
