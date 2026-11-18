"""Qualify the original canonical controls after active-work presentation rollback."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/compat-batch/K03-original-controls-r9'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, digest in read(cut / 'manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == digest, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_SCOPED_K03' and q['runner_exit_code'] == 0
assert q['browser_checks_passed'] == 19 and q['previous_S3_predicates_preserved'] == 13
assert q['new_original_form_checks'] == 6 and not q['UI_non_read_requests']
assert not q['UI_form_selection_or_decision'] and q['CLI_response_after_panel_closed']
assert not q['request_TTL_changed'] and q['provider_invocations'] == 0
assert q['guards_before'] == q['guards_after'] and not q['guards_after']['drift']
assert q['canonical_stop']['shutdown_outcome'] == 'drained'
assert not q['physical_same_birth_remaining'] and not q['listeners_after'] and not q['forced_containment']
assert not q['private_logs_copied'] and not q['cookie_or_token_copied']
browser = read(cut / 'browser-checks.json')
assert len(browser['checks']) == 19 and all(row['pass'] for row in browser['checks'])
assert not browser['writes']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Fresh installed R9, real foreground HTTP service, separate installed CLI processes and own-profile Chrome with canonical own human cookie; inert version/Test/native protocol peer',
    'command_or_procedure': 'During original active CLI work, use actual Settings classic/operational/classic; open the exact global question on classic Home, observe original approval GET and key, pending native form, original empty options and accessible Send/Deny/Check controls; close unchanged, let CLI answer/result/reconnect/close',
    'result': 'PASS19 browser predicates preserving all13 prior S3 checks plus6 original-control checks, with zero browser writes or answer selection. Same selected project/connection/request, strict profile/checkpoint/config/root/grant assertions and same owner; CLI responds after panel closes, normal drained service stop and physical/actual-port absence; source1829/payload1031/oldreadonly1028/tool192 unchanged',
    'limitations': 'K03 covers classic Home, canonical original controls and global bell. Conversations navigation is not claimed or required by this literal scenario. Selected protected data, not whole-DB immutability. Foreground service and inert peer, without Windows task/login/reboot, real provider, human acceptance or performance qualification.'}
test = next(test for test in ledger['tests'] if test['id'] == 'HST-T-K03')
test['status'] = 'PASS'
if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
    test['evidence'].append(entry)
test['execution_notes'] = 'PASS actual active-work rollback preserves classic Home, exact global question and original canonical form/controls; CLI continues after read-only UI inspection with selected invariants unchanged.'
ledger['execution']['r9_classic_controls'] = {
    'status': 'PASS_K03_ORIGINAL_CONTROLS', 'qualification': entry['artifact_path'],
    'browser_checks': 19, 'original_s3_checks_preserved': 13,
    'new_control_checks': 6, 'ui_writes': 0, 'provider_calls': 0,
    'canonical_service_stop': 'DRAINED', 'physical_absence': True}
pending = ledger['execution']['local_usability_candidate']['pending_local_scopes']
pending[:] = [item for item in pending if item != 'full classic-control navigation']
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'K03': 'PASS19', 'ui_writes': 0, 'human': 'NOT_INVITED'}))
