"""Read-only preparation: imports, --help and exact task-name absence only."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / 'venv/Scripts/python.exe'
ENV = json.loads((ROOT / 'environment.json').read_text())
NEXUS = ['-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main']
CONNECTOR = ['-I', '-B', '-m', 'okto_nexus_connector.cli.main']
home, state, project = ROOT / 'campaign/nexus', ROOT / 'campaign/connector', ROOT / 'campaign/project'
for path in (home, state, project):
    path.mkdir(parents=True, exist_ok=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (ROOT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def run(argv, label):
    # Only this closed allowlist is executed by the preparation tool.
    assert '--help' in argv or 'inspect_installed.py' in ' '.join(argv)
    with (ROOT / (label + '.stdout.txt')).open('x', encoding='utf-8') as out, \
         (ROOT / (label + '.stderr.txt')).open('x', encoding='utf-8') as err:
        process = subprocess.run(argv, env=ENV, cwd=project, stdout=out, stderr=err, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert process.returncode == 0, label + ' failed; inspect its retained diagnostic, no campaign was run.'
    return dict(argv=argv, returncode=process.returncode, stdout_sha256=sha(ROOT / (label + '.stdout.txt')),
        stderr_sha256=sha(ROOT / (label + '.stderr.txt')))


checks = []
checks.append(run([str(PYTHON), '-I', '-B', str(ROOT / 'inspect_installed.py'), '--output', 'installed-proof.json'], 'installed-inspection'))
checks.append(run([str(PYTHON.with_name('pythonw.exe')), '-I', '-B', str(ROOT / 'inspect_installed.py'),
    '--imports-only', '--output', 'pythonw-import-proof.json'], 'pythonw-imports'))
for label, command in (
    ('nexus-service-help', [*NEXUS, 'service', '--help']),
    ('connector-service-help', [*CONNECTOR, 'service', '--help']),
    ('connector-service-install-help', [*CONNECTOR, 'service', 'install', '--help']),
    ('connector-daemon-help', [*CONNECTOR, 'daemon', '--help']),
    ('connector-daemon-start-help', [*CONNECTOR, 'daemon', 'start', '--help']),
    ('connector-daemon-stop-help', [*CONNECTOR, 'daemon', 'stop', '--help'])):
    checks.append(run([str(PYTHON), *command], label))
write('read-only-checks.json', checks)
installed = json.loads((ROOT / 'installed-proof.json').read_text())
with socket.socket() as selected:
    selected.bind(('127.0.0.1', 0))
    port = selected.getsockname()[1]
common = ['--home', str(home), '--host', '127.0.0.1', '--port', str(port), '--project-root', str(project),
    '--embedding-mode', 'off', '--feature-harness-integrations', 'false', '--metrics-mode', 'disabled', '--json']


def command(component, action):
    if component == 'nexus':
        consent = ['--user', '--start-at-login'] if action == 'install' else ['--user'] if action in ('enable', 'disable', 'uninstall') else []
        return [str(PYTHON), *NEXUS, 'service', action, *consent, *common, '--timeout', '45']
    family = 'service' if action in ('install', 'enable', 'disable', 'uninstall', 'service-status') else 'daemon'
    actual = 'status' if action == 'service-status' else action
    duration = ['--timeout', '45'] if action in ('start', 'stop', 'restart') else []
    return [str(PYTHON), *CONNECTOR, '--state-dir', str(state), '--non-interactive', family, actual, *duration, '--json']


phases = [
    ('install', 0, 'Only the exact absent target becomes an enabled owned user task; no process is started.'),
    ('install', 0, 'Identical repeated install preserves task digest and installation ownership receipt; no second task.'),
    ('start', 0, 'Canonical readiness confirms selected instance, nonempty generation, current version and windows-task-scheduler supervisor.'),
    ('start', 0, 'Reuse preserves the first process birth/PID and generation; no second owner.'),
    ('disable', 0, 'Native task disabled; running generation remains alive; no drain inferred from disable.'),
    ('stop', 0, 'Canonical graceful drain confirmed, stopped state and exact prior process exit; no force termination.'),
    ('start', 'nonzero', 'Disabled task refuses startup and leaves no process owner.'),
    ('enable', 0, 'Native task enabled but remains stopped; enable does not start a process.'),
    ('start', 0, 'Canonical readiness returns a new generation of the same instance.'),
    ('restart', 0, 'Previous generation drains/exits before new generation becomes ready; no overlap.'),
    ('stop', 0, 'Final canonical drain and owner exit confirmed before uninstall.'),
    ('uninstall', 0, 'Only this owned stopped task is removed; data retained; target task read confirms absence.'),
]
steps = []
for component in ('nexus', 'connector'):
    for index, (action, code, expect) in enumerate(phases, 1):
        steps.append(dict(id=f'{component}-{index:02d}-{action}', component=component, action=action,
            argv=command(component, action), expect_returncode=code, required_evidence=expect,
            followup_status_argv=command(component, 'status'),
            followup_native='Read only the exact target task; retain enabled/state/digest, never token-bearing raw XML.'))
    if component == 'connector':
        steps[-1]['followup_service_status_argv'] = command(component, 'service-status')

heads = {}
for name, repo in [('nexus', 'D:/Projetos/Techridy/okto_labs_okto_nexus'),
                  ('connector', 'D:/Projetos/Techridy/okto-nexus-connector'),
                  ('core', 'D:/Projetos/Techridy/okto-nexus-connector-core')]:
    commit = subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip()
    clean = not subprocess.check_output(['git', '-C', repo, 'status', '--porcelain'], text=True).strip()
    assert clean
    heads[name] = dict(repository=repo, commit=commit, clean_at_preparation=True)
proposal = dict(revision=2, status='PREPARED_NOT_AUTHORIZED_NOT_RUN', prepared_at=datetime.now(timezone.utc).isoformat(),
    root=str(ROOT), python=str(PYTHON), pythonw=str(PYTHON.with_name('pythonw.exe')), server_home=str(home),
    server_database=str(home / 'nexus.db'), connector_state=str(state), project_root=str(project), host='127.0.0.1', port=port,
    current_sources=heads, packages={name:{key:value[key] for key in ('version','wheel','wheel_sha256','file_count','import_path')}
        for name,value in installed['packages'].items()},
    installed_proof_sha256=sha(ROOT / 'installed-proof.json'), pythonw_proof_sha256=sha(ROOT / 'pythonw-import-proof.json'),
    dependency_preparation_sha256=sha(ROOT / 'environment-preparation.json'), environment=ENV,
    task_names={name:value['task_name'] for name,value in installed['task_observations'].items()},
    native_absence_verified=True, native_calls_executed=['WindowsTasks.read(nexus exact target)', 'WindowsTasks.read(connector exact target)'],
    native_calls_not_executed=['validate/RegisterTask', 'create', 'Run', 'Enabled mutation', 'DeleteTask'],
    scope='After explicit authorization only: these two temporary user tasks, these empty homes and this disposable installed interpreter.',
    preconditions=['Recheck the exact task names absent and these homes empty immediately before install.',
        'Recheck loopback port free; do not silently choose another port after approval.',
        'Recheck immutable wheel/import/environment hashes; preserve failure if mismatched.',
        'No existing personal state is adopted. A foreign/legacy conflicting task is preserved and the campaign stops.'],
    effect_boundaries=['24 finite lifecycle actions (12 per component), with bounded read-only status/readiness/native-definition observations.',
        'Native registration creates user logon triggers; no logout/reboot or logon trigger execution is part of this campaign.',
        'Nexus uses harness integrations false, embedding off, metrics disabled and an empty store; no discovery/provider execution.',
        'Connector has no identities, servers or executor registrations. Its file-vault backend is selected but not approved or used; no credential imports or resolutions.',
        'Task Scheduler action receives a generated installation ownership token only at authorized install. Do not retain raw XML/argv containing that token; record digest and sanitized action shape.'],
    excluded=['Personal homes/state/vaults or provider credentials', 'provider requests/paid turns', 'logout/reboot',
        'forced stop/kill/task termination', 'existing-task overwrite/adoption', 'registry/startup settings outside the two tasks',
        'service upgrades or extra recovery campaigns', 'API-key creation/rotation or execution grants'],
    steps=steps, observation_bound_seconds=45,
    abort_policy='On mismatch or unconfirmed native/process state, stop progression. Preserve receipts; do not force cleanup, adopt another task, or retry mutations blindly.',
    cleanup='Canonical stop then owner/digest-fenced uninstall of each exact target. Verify DRAINED/exit, both tasks absent and no live owner; retain disposable data/evidence. If uncertain, report remaining exact references.',
    limits=['Preparation is not a native-service qualification. No lifecycle action has been executed.',
        'No evidence of logout/reboot survival, real-provider readiness, client participation, or M1/M2 completion is claimed.'],
    pending_authorization='Create/manage/remove only the two named temporary per-user Task Scheduler tasks through the listed installed CLIs; start/reuse/drain/restart only their two empty isolated runtimes.')
write('native-service-campaign-proposal.json', proposal)
print(json.dumps(dict(proposal=str(ROOT / 'native-service-campaign-proposal.json'), proposal_sha256=sha(ROOT / 'native-service-campaign-proposal.json'),
    task_names=proposal['task_names'], checks=len(checks), campaign_executed=False), indent=2))
