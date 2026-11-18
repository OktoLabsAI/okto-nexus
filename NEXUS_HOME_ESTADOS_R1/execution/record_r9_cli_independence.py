"""Record the fresh candidate CLI cycle that never opened a dashboard."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/compat-batch/K05-candidate-r9'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, digest in read(cut / 'manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == digest, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_K05_CANDIDATE_WITHOUT_DASHBOARD'
assert q['runner_exit_code'] == q['server_process_exit_code'] == 0
assert q['phase'] == 'current-cli' and q['CLI_documents'] == 14
assert q['HTTP_requests'] == 150 and not q['dashboard_HTTP_requests']
assert not q['browser_started'] and not q['browser_marker_written'] and not q['browser_births']
assert q['owner_before'] == q['owner_after'] and q['canonical_stop']['shutdown_outcome'] == 'drained'
assert q['actual_audited_ports'] and not q['listeners_after'] and not q['physical_same_birth_remaining']
assert not q['forced_containment'] and q['guards_before'] == q['guards_after']
assert not q['guards_after']['drift'] and q['provider_invocations'] == 0
assert not q['cookie_or_token_copied'] and not q['private_logs_copied']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Fresh installed R9 candidate; separate installed CLI subprocesses and real foreground HTTP service; inert version/Test/native protocol peers; canonical own account is fixture precondition',
    'command_or_procedure': 'Without any dashboard/browser: CLI connect review/exact approval, work send/status, exact-recipient answer review/confirmation, result, reconnect with selected invariant assertions, exact close and final status --control',
    'result': 'PASS14 CLI public documents and150 API request traces; zero dashboard HTML/assets, Chrome/Node births or browser marker; same owner PID/birth/instance/generation, reconnect config/root/grant/checkpoint/Test/probe unchanged; exact close SUCCEEDED/session CLOSED, service stop drained, physical0 and actual port audit0; source1829/R9payload1031/oldreadonly1028/tool192 unchanged',
    'limitations': 'Fresh candidate qualification, not inherited from S3 or old producer. Synthetic protocol peer is not Codex/provider qualification; no Windows Connector daemon task/login lifecycle or human acceptance. Selected snapshot digests were asserted by the successful pinned process and not separately logged. API fixture account creation is not a web UI step.'}
test = next(test for test in ledger['tests'] if test['id'] == 'HST-T-K05')
test['status'] = 'PASS'
if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
    test['evidence'].append(entry)
test['execution_notes'] = 'PASS fresh candidate no-dashboard CLI cycle and strict reconnect invariants; actual separate foreground service/CLI/native inert peer, no real provider or Windows task qualification.'
ledger['execution']['r9_cli_without_dashboard'] = {
    'status': 'PASS_K05_CANDIDATE', 'qualification': entry['artifact_path'],
    'cli_documents': 14, 'http_api_requests': 150, 'dashboard_requests': 0,
    'provider_calls': 0, 'canonical_close': 'SUCCEEDED_AND_CLOSED',
    'canonical_service_stop': 'DRAINED', 'physical_absence': True}
pending = ledger['execution']['local_usability_candidate']['pending_local_scopes']
pending[:] = ['full classic-control navigation'
             if item == 'no-dashboard CLI and full classic-control navigation' else item
             for item in pending]
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'K05': 'PASS_FRESH_CANDIDATE', 'dashboard': False, 'provider_calls': 0}))
