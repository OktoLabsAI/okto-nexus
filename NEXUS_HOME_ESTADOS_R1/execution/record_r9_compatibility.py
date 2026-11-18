"""Record actual installed CLI/HTTP presentation rollback, without K05 inflation."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/compat-batch/attempt2-s3-r9'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, expected in read(cut / 'manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == expected, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_SCOPED_S3' and q['runner_exit_code'] == 0
assert q['browser_checks_passed'] == 13 and len(q['CLI_commands']) == 14
assert all(row['exit_code'] == 0 for row in q['CLI_commands'])
assert q['guards_before'] == q['guards_after'] and not q['guards_after']['drift']
assert not q['physical_same_birth_remaining'] and not q['listeners_after']
assert not q['forced_containment'] and q['provider_invocations'] == 0
assert q['canonical_stop']['state'] == 'stopped'
assert q['canonical_stop']['shutdown_outcome'] == 'drained'
assert not q['cookie_or_token_copied'] and not q['private_logs_copied']
owner = read(cut / 'owner-proof.json')
assert owner['before'] == owner['after'] and owner['birth_before'] == owner['birth_after']
assert owner['same_owner_across_ui_and_cli']
browser = read(cut / 'browser-checks.json')
assert all(check['pass'] for check in browser['checks']) and not browser['writes']
for action in ('turn.submit', 'runtime.close'):
    assert any(row['action'] == action and row['latest_stage'] == 'SUCCEEDED'
               for row in q['canonical_operations'])
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Fresh installed R9, real foreground Nexus run_serve/ServiceLifecycle, separate installed CLI processes, own-profile Chrome; synthetic version/Test/native protocol peer',
    'command_or_procedure': 'Canonical CLI connect/work and original native question; actual Settings classic/operational/classic toggle during that work; exact global question; CLI answer/result/reconnect/close with strict config/root/grant/checkpoint and owner assertions',
    'result': 'PASS13 browser checks and14 installed CLI commands; UI writes0; same PID/birth/instance/generation throughout; selected config/grants/root/checkpoint unchanged by UI and reconnect; actual turn.submit and runtime.close SUCCEEDED; canonical service stop drained, physical0, source1829/R9payload1031/oldreadonly1028/tool192 drift0',
    'limitations': 'Own foreground Nexus service, not Windows scheduled task or real Connector daemon qualification. Browser was open, so K05 no-dashboard is not qualified. Classic session summary/project/global question were exposed, but full classic Conversations/control navigation was not exercised. Selected invariant digests were compared by the successful pinned CLI process but not separately logged; post hashes are not fabricated. No real provider/human/performance claim.'}
for test in ledger['tests']:
    if test['id'] in ('HST-T-H10', 'HST-T-K03', 'HST-T-K05') and not any(
        old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']
    ):
        test['evidence'].append(entry)
    if test['id'] == 'HST-T-H10':
        test['status'] = 'PASS'
        test['execution_notes'] = 'PASS local installed foreground-service variant: actual UI rollback while CLI work remains, strict root/identity/grant/checkpoint invariants and same live owner PID/birth/instance/generation; no Windows service-task/real Connector daemon claim.'
    if test['id'] == 'HST-T-K03':
        test['execution_notes'] = 'PARTIAL actual active-work rollback: classic summary/project/global question reachable and CLI/canonical data retained; full classic controls/Conversations navigation not exercised. No whole-scenario promotion.'
    if test['id'] == 'HST-T-K05':
        test['execution_notes'] = 'PARTIAL actual installed connect/work/answer/result/reconnect/close passes without web intervention in the CLI decisions, but the dashboard was already open for S3. A separate no-dashboard candidate cut is required.'
ledger['execution']['r9_compatibility_s3'] = {
    'status': 'PASS_SCOPED_FOREGROUND_UI_ROLLBACK', 'qualification': entry['artifact_path'],
    'browser_checks': 13, 'cli_commands': 14, 'owner_preserved': True,
    'protected_invariants': 'EXECUTED_ASSERTIONS; POST_DIGEST_VALUES_NOT_SEPARATELY_LOGGED',
    'canonical_stop': 'DRAINED', 'physical_absence': True,
    'K03': 'PARTIAL_CLASSIC_CONTROL_NAVIGATION_NOT_RUN',
    'K05': 'NO_DASHBOARD_NOT_RUN', 'S4': 'NOT_RUN'}
pending = ledger['execution']['local_usability_candidate']['pending_local_scopes']
pending[:] = ['no-dashboard CLI and full classic-control navigation'
             if item == 'foreground CLI and active presentation rollback' else item
             for item in pending]
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'H10': 'PASS_LOCAL_FOREGROUND', 'K03': 'PARTIAL', 'K05': 'PARTIAL'}))
