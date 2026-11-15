"""Conditional SVC20 Connector next-connect; no effects at import.

Execute only after a real DONE and proven zero admissions. The post-paid branch
is held until an actual session settlement companion is available and reviewed.
Terminal receipts alone are deliberately insufficient. The original
paid context cannot be reused after this deliberate Connector generation change.
"""
from pathlib import Path
from contextlib import closing
import argparse
import json
import sqlite3
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
RECOVERY = HERE.parent
sys.path.insert(0, str(RECOVERY))
from recovery_context import RecoveryContext, require, read_json, sha, pin, reserve
import recovery_observation as observed
import recovery_connector as connector


def connect_args(plan):
    # Connector has no --no-chat; no --start selects no productive runtime.
    return ['--state-dir', plan['paths']['connector_state'], 'connect',
            '--identity', plan['agent_id'], '--request-id', 'm1-sonnet-remote-setup-02',
            '--server', plan['origin'], '--project', plan['paths']['connector_project']]


def validate_completed(plan, completed, profile, rotation):
    require(completed.get('profile') == plan['profile'] == 'm1-sonnet-remote-recovery02'
            and completed.get('current_credential_epoch') == 2
            and completed.get('material_status') == 'reuse_existing', 'REAL_RECOVERY_DONE_REQUIRED')
    require(profile.get('state') == 'done' and profile.get('result', {}).get('saved') is True
            and profile.get('remote_scope') == completed.get('remote_scope'), 'PROFILE_NOT_CANONICAL_DONE')
    scope = completed['remote_scope']
    require(scope.get('agent_id') == plan['agent_id'] == 'm1-sonnet-remote'
            and scope.get('server_id') == plan['server_id']
            and scope.get('workspace_id') == plan['workspace_id']
            and scope.get('adapter_id') == 'claude_stream', 'COMPLETED_SCOPE_CHANGED')
    require(rotation.get('status') == 'ROTATED_ONCE_IMPORTED_ONCE'
            and rotation.get('current_epoch') == 2 and rotation.get('agent_id') == plan['agent_id']
            and rotation.get('server_id') == plan['server_id'], 'REAL_ROTATION_IMPORT_REQUIRED')
    return scope


def accounting(database, plan):
    """Selected canonical counters only; never credential or semantic payload columns."""
    with closing(sqlite3.connect(Path(database).as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        db.execute('PRAGMA query_only=ON')
        end = time.monotonic() + 2
        db.set_progress_handler(lambda: int(time.monotonic() > end), 1000)
        args = (plan['server_id'], plan['agent_id'], plan['workspace_id'])
        rows = db.execute('''SELECT o.operation_id,
            (SELECT r.stage FROM execution_receipts r WHERE r.server_id=o.server_id
             AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id
             ORDER BY r.receipt_revision DESC LIMIT 1)
            FROM execution_operations o WHERE o.server_id=? AND o.subject_agent_id=? AND o.workspace_id=?
            ORDER BY o.operation_id''', args).fetchall()
        # No current paid companion proves Core release/session settlement.
        # Even SUCCEEDED is not a release proof. Do not invent one from receipts.
        require(not rows, 'POST_PAID_SETTLEMENT_PROOF_REQUIRED_NO_STOP_ALLOWED')
        grants = db.execute('''SELECT grant_id,revision,max_executions,used_executions,expires_at,revoked_at
            FROM runtime_execution_grants WHERE represented_agent_id=? AND workspace_id=? ORDER BY grant_id''',
            (plan['agent_id'], plan['workspace_id'])).fetchall()
        require(bool(grants), 'EXISTING_GRANT_REQUIRED')
    return {'operation_ids': [row[0] for row in rows], 'operation_count': len(rows),
            'terminal_stages': [row[1] for row in rows], 'grants': [list(row) for row in grants]}


class Context:
    def __init__(self, path, expected):
        require(Path(path).resolve() == HERE / 'selected-plan.json' and sha(path) == expected, 'SELECTED_PLAN_CHANGED')
        self.P = read_json(path)
        require(self.P['status'] == 'ROOT_SELECTED_AFTER_REAL_DONE_AND_ZERO_ADMISSIONS', 'FUTURE_SELECTION_REQUIRED')
        for item in self.P['pins'].values():
            pin(item)
        lp = self.P['lifecycle_plan']
        self.base = RecoveryContext(pin(lp), lp['sha256'])
        self.plan_sha = expected
        self.PUBLIC, self.PRIVATE = HERE / 'public', HERE / 'private'
        for key, value in self.P['paths'].items():
            require(Path(value).resolve() == Path(self.base.P['paths'][key]).resolve(), 'OWN_PATH_CHANGED')
        completed = read_json(pin(self.P['completed']))
        rotation = read_json(pin(self.P['rotation']))
        require(completed['rotation_import_result_pin']['sha256'] == self.P['rotation']['sha256'], 'DONE_ROTATION_CHAIN_CHANGED')
        profile = Path(self.P['paths']['operator_home']) / 'terminal/profiles' / (self.P['profile'] + '.json')
        require(sha(profile) == completed['profile_sha256'], 'DONE_PROFILE_CHANGED')
        self.scope = validate_completed(self.P, completed, read_json(profile), rotation)
        require(self.P['settlement_gate'] == 'ZERO_EXECUTION_OPERATIONS_ONLY'
                and self.P['post_paid_branch'] == 'HELD_NO_SETTLEMENT_COMPANION', 'NO_CONCURRENT_PAID_WORK')
        self.handles = []
        self.children = []
        self.connect_selected = False
        self.post_connect_capture_complete = False

    def save(self, name, value):
        reserve(self.PUBLIC / name, dict(value, next_connect_plan_sha256=self.plan_sha))

    def counters(self):
        return accounting(Path(self.P['paths']['server_home']) / 'nexus.db', self.P)

    def nexus_ready(self):
        current = self.base.require_nexus_ready()
        observed.same_owner(self.nexus_selected, current)
        observed.same_cycle(self.nexus_selected['cohort'], current['cohort'])

    def capture(self):
        selection, handles = connector.capture(self.base)
        self.handles.extend(handles.values())
        return selection, handles

    def cli(self, name, argv):
        self.save(name + '-reserved.json', {'argv': argv, 'force_used': False})
        with (self.PRIVATE / (name + '.stdout')).open('xb') as out, (self.PRIVATE / (name + '.stderr')).open('xb') as err:
            child = subprocess.Popen(argv, cwd=self.base.ROOT, env=self.base.connector_env(),
                stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            self.children.append(child)
            try:
                code = child.wait(timeout=180)
            except subprocess.TimeoutExpired:
                raise RuntimeError('CLI_PENDING_NO_CONCURRENT_STOP') from None
        self.save(name + '-returned.json', {'returncode': code, 'stdout_sha256': sha(self.PRIVATE / (name + '.stdout')),
                  'stderr_sha256': sha(self.PRIVATE / (name + '.stderr'))})
        require(code == 0, 'CLI_UNCONFIRMED_NO_REPLAY')

    def stop(self, label, selection, handles):
        self.nexus_ready()
        self.counters()  # Refuse to stop if productive admission appeared.
        observed.same_owner(selection, observed.status(self.base, 'connector'))
        observed.same_cycle(selection['cohort'], connector.cycle(self.base))
        self.cli(label, connector.stop_argv(self.base))
        end = time.monotonic() + 60
        while time.monotonic() < end and not all(h.exited() for h in handles.values()):
            time.sleep(.2)
        require(all(h.exited() for h in handles.values()), 'CONNECTOR_PHYSICAL_EXIT_UNCONFIRMED')
        self.save(label + '-exit-proof.json', {'cohort': selection['cohort'],
            'exits': {role: {'pid': h.pid, 'birth': h.birth, 'physical_exit': True, 'exit_code': h.exit_code()}
                      for role, h in handles.items()}, 'force_used': False})
        end = time.monotonic() + 30
        while True:
            _, task = connector.installation(self.base).observe()
            if task is not None and not task.active:
                break
            require(time.monotonic() < end, 'NATIVE_TASK_NOT_INACTIVE')
            time.sleep(.2)
        require(task.digest == selection['task']['digest'], 'TASK_DEFINITION_CHANGED')
        observed.canonical_absence(self.base, 'connector')

    def handoff_and_close(self, error=None):
        if error:
            try:
                self.save('failure.json', {'status': 'UNCONFIRMED_NO_REPLAY', 'error_type': type(error).__name__,
                    'cleanup_claimed': False, 'force_used': False, 'new_control_selected': False})
            except OSError:
                pass
            end = time.monotonic() + 7200
            while time.monotonic() < end:
                try:
                    cohort_complete = not self.connect_selected or self.post_connect_capture_complete
                    if cohort_complete and self.handles and all(h.exited() for h in self.handles) and all(c.poll() is not None for c in self.children):
                        break
                except Exception:
                    pass  # Unknown observation never releases a live cohort early.
                time.sleep(.5)
        for handle in self.handles:
            handle.close()


def worker(context):
    from okto_nexus_connector.cli.main import main
    from okto_nexus_connector.cli.commands import connect, configure_local
    from okto_nexus_connector.transport.https_client import NexusHTTPClient
    from okto_nexus_connector.errors import ConnectorError
    original, request = connect.run_connect, NexusHTTPClient._request
    captured = {}

    async def no_new_setup(*args, **kwargs):
        raise ConnectorError('SVC20_UNEXPECTED_SETUP', 'connect', 'Only completed configured reuse was selected.')

    async def get_only(self, method, path, **kwargs):
        if method != 'GET':
            raise ConnectorError('SVC20_UNEXPECTED_EFFECT', 'connect', 'Only setup GET observations were selected.')
        return await request(self, method, path, **kwargs)

    async def observe_result(*args, **kwargs):
        value = await original(*args, **kwargs)
        captured.update(value)
        return value

    configure_local.configure_local = no_new_setup
    connect._choose_harness = no_new_setup
    NexusHTTPClient._request = get_only
    connect.run_connect = observe_result
    code = main(connect_args(context.P))
    require(code == 0 and captured.get('saved') is True and captured.get('reused') is True
            and captured.get('runtime_started') is False, 'CONFIGURED_REUSE_NOT_CONFIRMED')
    binding = captured.get('current_binding', {})
    require(all(binding.get(k) == value for k, value in context.scope.items()), 'REUSED_BINDING_SCOPE_CHANGED')
    context.save('configured-connect-observed.json', {'saved': True, 'reused': True, 'runtime_started': False,
        'binding_id': binding['binding_id'], 'request_id': captured.get('request_id'), 'new_setup': False,
        'worker_http_methods': ['GET'], 'provider_calls_selected': 0})


def run(context):
    require(not context.PUBLIC.exists() and not context.PRIVATE.exists(), 'SELECTION_ALREADY_EXISTS')
    context.PUBLIC.mkdir()
    observed.secure_directory(context.PRIVATE, HERE)
    failure = None
    try:
        context.nexus_selected = context.base.require_nexus_ready()
        context.base.require_ready()
        before = context.counters()
        first, handles = context.capture()
        context.save('before.json', {'connector': first, 'accounting': before})
        context.stop('initial-stop', first, handles)
        context.nexus_ready()
        observed.canonical_absence(context.base, 'connector')
        context.save('stopped-before-next-connect.json', {'old_cohort_physically_exited': True,
            'canonical_absence': True, 'native_inactive': True, 'historical_quiet_190_not_repeated': True})
        context.connect_selected = True
        context.cli('configured-connect', [context.base.python, '-I', '-B', '-X', 'utf8', str(Path(__file__)),
            '--plan', str(HERE / 'selected-plan.json'), '--expected-plan-sha256', context.plan_sha, 'worker'])
        current, new_handles = context.capture()
        context.post_connect_capture_complete = True
        require(current['generation'] != first['generation'] and current['cohort']['cycle_id'] != first['cohort']['cycle_id'],
                'NEW_CANONICAL_CONNECT_COHORT_REQUIRED')
        context.save('after-connect-cohort.json', current)
        context.nexus_ready()
        require(context.counters() == before, 'CONNECT_CREATED_OPERATION_OR_CHANGED_GRANT')
        context.stop('final-stop', current, new_handles)
        require(context.counters() == before, 'FINAL_ACCOUNTING_CHANGED')
        context.save('result.json', {'status': 'PASS_SCOPED', 'configured_next_connect': True,
            'new_execution_operations': 0, 'same_binding_grants': True, 'both_connector_cohorts_exited': True,
            'connector_task_retained_inactive': True, 'nexus_same_ready_cohort': True, 'force_used': False,
            'productive_start_selected': False, 'provider_calls_selected': 0,
            'paid_context_invalidated_by_generation_change': True})
    except BaseException as error:
        failure = error
        raise
    finally:
        context.handoff_and_close(failure)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('action', choices=('run', 'worker'))
    args = parser.parse_args()
    selected = Context(args.plan, args.expected_plan_sha256)
    (run if args.action == 'run' else worker)(selected)
