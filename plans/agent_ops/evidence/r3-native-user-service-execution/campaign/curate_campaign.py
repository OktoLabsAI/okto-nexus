"""Closed public allowlist for the completed empty-runtime campaign."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public-campaign'
PROPOSAL = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-campaign-proposals/native-service-campaign-proposal.json')
PLAN = json.loads(PROPOSAL.read_text(encoding='utf-8'))
FINAL = json.loads((ROOT / 'execution-001-resume2/execution-record.json').read_text())
assert FINAL['status'] == 'PASS' and len(FINAL['passed']) == 24
assert [x['id'] for x in FINAL['passed']] == [x['id'] for x in PLAN['steps']]
assert len({x['id'] for x in FINAL['passed']}) == 24
assert all(FINAL[key] is True for key in ('cleanup_confirmed', 'tasks_absent', 'owners_exited', 'listener_closed', 'packages_unchanged'))


def digest(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def write(relative, value):
    path = PUBLIC / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    allowlist.append(relative)


def copy(source, relative):
    target = PUBLIC / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    allowlist.append(relative)


PUBLIC.mkdir(exist_ok=False)
allowlist = []
copy(PROPOSAL, 'proposal-revision4.json')
copy(Path(__file__), 'curate_campaign.py')
for revision, filename, directory in (
        (1, 'execute_campaign.py', 'execution-001'),
        (2, 'execute_campaign_v2.py', 'execution-001-resume'),
        (3, 'execute_campaign_v3.py', 'execution-001-resume2')):
    copy(ROOT / filename, f'runners/v{revision}.py')
    for name in ('preflight.json', 'execution-record.json', 'active-command.json'):
        copy(ROOT / directory / name, f'attempt-{revision}/{name}')
    failure = ROOT / directory / 'failure.json'
    if failure.exists():
        copy(failure, f'attempt-{revision}/failure.json')
copy(ROOT / 'execution-001-resume/execution-record.json.tmp', 'attempt-2/unpublished-checkpoint.json')

post = {}
for dist, item in PLAN['packages'].items():
    installed = Path(item['import_path'])
    wheel = Path(item['wheel'])
    assert digest(wheel)['sha256'] == item['wheel_sha256']
    with zipfile.ZipFile(wheel) as archive:
        prefix = installed.name + '/'
        expected = {name[len(prefix):]: hashlib.sha256(archive.read(name)).hexdigest()
                    for name in archive.namelist() if name.startswith(prefix) and not name.endswith('/')}
    actual = {path.relative_to(installed).as_posix(): digest(path)['sha256'] for path in installed.rglob('*')
              if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo')}
    assert actual == expected and len(actual) == item['file_count']
    post[dist] = {'version': item['version'], 'wheel_sha256': item['wheel_sha256'],
                  'files': actual, 'file_count': len(actual), 'wheel_equals_installed': True}
write('post-package-proof.json', {'at': datetime.now(timezone.utc).isoformat(), 'packages': post,
                                'total_package_files': sum(x['file_count'] for x in post.values())})

rows = []
for step, evidence in zip(PLAN['steps'], FINAL['passed'], strict=True):
    code = evidence['action']['returncode']
    expected = step['expect_returncode']
    assert code != 0 if expected == 'nonzero' else code == expected
    phase = int(step['id'].split('-')[1])
    row = {'id': step['id'], 'component': step['component'], 'action': step['action'],
           'expected_returncode': expected, 'actual_returncode': code,
           'literal_required_evidence': step['required_evidence'], 'result': 'PASS',
           'evidence': evidence,
           'native_effect_invocations_for_this_step': 1,
           'resume_observation_not_an_extra_action': step['id'] == 'nexus-01-install'}
    if phase == 10:
        row['ordering_oracle'] = {'assertion_passed': True,
            'predicate': 'old held HANDLE exited and old exit FILETIME <= new birth FILETIME',
            'recording_limit': 'The assertion ran before PASS; the exact old exit FILETIME for restart was not retained separately.'}
    rows.append(row)
    copy_from = ('execution-001' if step['id'] == 'nexus-01-install' else
                 'execution-001-resume' if step['component'] == 'nexus' and phase <= 4 else
                 'execution-001-resume2')
    for suffix in ('.json', '-status.json'):
        copy(ROOT / copy_from / (step['id'] + suffix), 'commands/' + step['id'] + suffix)
    if step['id'] == 'connector-12-uninstall':
        copy(ROOT / copy_from / (step['id'] + '-service-status.json'), 'commands/' + step['id'] + '-service-status.json')
write('actions.json', {'unique_action_count': 24, 'mutating_cli_invocations': 24, 'rows': rows})

write('harness-history.json', {'failures_preserved': [
    {'attempt': 1, 'kind': 'observer_comparison_error', 'effect_committed': 'nexus-01-install',
     'failure': 'RECORDED_ENVIRONMENT_MISMATCH', 'actual_difference': 'PATH Windows directory casing',
     'resolution': 'Apply the installed context Path.resolve/deduplication contract to the expected PATH only; no argv/env change; no repeat install1.'},
    {'attempt': 2, 'kind': 'evidence_writer_error', 'completed_actions': 4,
     'failure': 'PermissionError WinError5 on os.replace; failure handler encountered the same write error.',
     'effect_5_emitted': False, 'evidence': 'Retained four passed/attempted entries; active command status4; source line before command5 failed.',
     'limitation': 'Observer process exited and closed its handles. Cause of the OS denial was not established.',
     'resolution': 'Bounded one-second write retry for WinError5/32; robust error handler; re-acquired same PID/birth/generation/instance before resuming action5.'}],
    'action_retries_outside_proposal': 0, 'native_force_or_kill': False,
    'preparation_note': 'One PowerShell text-generation parse failure occurred before V2 file creation; no native/CLI action was invoked by that preparation failure.'})

write('qualification.json', {'status': 'PASS', 'unique_actions': 24,
    'authorization_quote': 'sim pode executar', 'proposal_revision': 4,
    'proposal_sha256': digest(PROPOSAL)['sha256'],
    'final_record': 'attempt-3/execution-record.json', 'cleanup_confirmed': True,
    'tasks_absent': PLAN['task_names'], 'all_observed_owners_exited': True,
    'listener_closed': {'host': '127.0.0.1', 'port': 52106},
    'post_wheel_and_installed_payloads_unchanged': True,
    'package_file_count': 981,
    'homes_retained': {key: Path(PLAN[key]).exists() for key in ('server_home', 'connector_state')},
    'supports': [
        {'id': 'SVC-T07', 'scope': 'Installed user tasks start the owned empty runtimes and canonical readiness confirms identity/version/supervisor.'},
        {'id': 'SVC-T14', 'scope': 'Explicit native enable/disable observed; disable preserves live owner and refuses later start; enable alone stays stopped.'},
        {'id': 'SVC-T17', 'scope': 'PARTIAL: repeated install and repeated start preserve definition/owner; no crash/adoption/recovery campaign.'},
        {'id': 'SVC-T20', 'scope': 'PARTIAL: canonical graceful stop of empty runtimes, drained outcome and process exit; no nonempty backlog or forced stop.'},
        {'id': 'SVC-T27', 'scope': 'PARTIAL: owner/digest-fenced uninstall removes only the two stopped tasks and retains homes; no post-uninstall foreground launch.'}],
    'not_qualified': ['logon trigger execution', 'logout', 'reboot', 'crash', 'suspension',
                      'foreground after uninstall', 'provider readiness', 'credential resolution', 'M1', 'M2'],
    'public_artifact_policy': 'Only explicit allowlist; no raw XML, token-bearing argv, contexts, DBs, homes, credentials or raw child output.'})

manifest = {'format': 1, 'files': {name: digest(PUBLIC / name) for name in allowlist}}
(PUBLIC / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
assert {p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob('*') if p.is_file()} == set(allowlist) | {'artifact-manifest.json'}
print(json.dumps({'public': str(PUBLIC), 'payload_count': len(allowlist),
                  'manifest': digest(PUBLIC / 'artifact-manifest.json'), 'unique_actions': 24}))
