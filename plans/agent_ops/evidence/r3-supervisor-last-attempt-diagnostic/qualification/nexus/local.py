"""Short-lived lifecycle adapter; the foreground Server owns its own lifetime."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import os
import json
from pathlib import Path
import secrets
import subprocess
import time
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import HTTPError

from ..process_liveness import process_exited
from .context import CONTEXT_NAME, atomic_json, document_revision, read_json, validate_context
from .inspection import NoRedirect, _held, inspect_local_server
from .locking import ExclusiveFileLock, LockBusy
from .installation import (INSTALLATION_NAME, SUPERVISOR,
                           ServerInstallation, InstallationError, installation_failure)

LAUNCH_NAME = 'service-launch.json'


@contextmanager
def launch_exclusion(home: Path, database: Path):
    held = []
    try:
        for path in sorted({home / 'service-launch.guard',
                            database.with_name(database.name + '.launch.guard')}):
            lock = ExclusiveFileLock(path)
            lock.acquire()
            held.append(lock)
        yield
    finally:
        for lock in reversed(held):
            lock.release()


class LocalServerLifecycle:
    def __init__(self, *, home, database, host, port, context=None, installation=None):
        self.home, self.database = Path(home).resolve(), Path(database).resolve()
        self.host, self.port, self.context = host, port, context
        self.installation = installation or ServerInstallation(self.home, self.database)

    def logs(self, *, tail=50, cursor=None):
        from .logs import read_logs
        return read_logs(self.home, tail=tail, cursor=cursor)

    def upgrade_plan(self, *, executable):
        from .upgrade import for_lifecycle
        return for_lifecycle(self).plan(executable)

    def login_start_review(self):
        from .login_start import review
        return review(self)

    def check_login_start_review(self, plan):
        from .login_start import validate
        validate(self, plan)

    def upgrade_apply(self, *, document, expected_revision):
        from .upgrade import for_lifecycle
        return for_lifecycle(self).apply(document, expected_revision)

    def inspect(self, *, timeout=2.0, _launch_owned=False):
        result = self._inspect_process(timeout=timeout)
        try:
            context = read_json(self.home / CONTEXT_NAME)
        except FileNotFoundError:
            context = {}
        except (OSError, ValueError):
            return {**result, 'state': 'unknown', 'reason': 'SERVICE_CONTEXT_UNAVAILABLE',
                'next_action': 'Restore the recorded service context before changing lifecycle state.'}
        if context.get('upgrade_pending'):
            return {**result, 'state': 'unknown', 'reason': 'SERVICE_UPGRADE_PENDING',
                'upgrade': {'plan_revision': context['upgrade_pending'], 'state': 'pending'},
                'next_action': 'Resume upgrade-apply with the retained plan before starting this instance.'}
        if result['state'] == 'stopped' and not _launch_owned and any(_held(path) is True for path in (
                self.home / 'service-launch.guard', self.database.with_name(self.database.name + '.launch.guard'))):
            return {**result, 'state': 'starting', 'reason': 'CONCURRENT_START',
                'next_action': 'Wait for the lifecycle selection already in progress.'}
        if not (self.home / INSTALLATION_NAME).exists():
            return result
        try:
            receipt, task = self.installation.observe()
            control = self.installation.control(receipt)
        except (OSError, ValueError, ImportError) as error:
            return installation_failure(result, error)
        actual_supervisor = result.get('supervisor')
        result = {**result, 'supervisor': SUPERVISOR, 'user_service': {
            'name': receipt['name'], 'state': task.state, 'enabled': task.enabled,
            'last_result': task.last_result, 'start_at_login': task.enabled,
            'available_before_login': False, 'available_after_logout': False,
            'definition_digest': receipt['native_digest']}}
        if result['state'] in {'ready', 'stopping'} and result.get('generation'):
            if actual_supervisor != SUPERVISOR:
                return {**result, 'state': 'failed', 'reason': 'SUPERVISOR_MISMATCH',
                    'next_action': 'The current owner is outside the installed task; reconcile the selected supervisor.'}
            if control['desired'] == 'draining':
                result = {**result, 'state': 'stopping', 'reason': 'RUNTIME_DRAINING',
                    'next_action': 'Repeat stop to observe this drain; start cannot reopen admission.'}
        elif (result['state'] == 'stopped' and control['desired'] == 'running'
                and task.state == 3 and task.last_result in {1, 2, 3}):
            # Runtime entry clears launch_requested. Its later failure still
            # needs diagnosis; a historical exit code does not prove that the
            # current launch or Scheduler retry budget has been exhausted.
            result = {**result, 'state': 'unknown', 'reason': 'SUPERVISOR_LAST_ATTEMPT_FAILED',
                'next_action': 'The last observed scheduled attempt failed; the current launch and retry outcome are unconfirmed. '
                    'Inspect the selected task and startup diagnostics. Use service stop before an explicit retry; no launch was repeated.'}
        elif result['state'] == 'stopped' and (task.active or task.state == 0 or control.get('launch_requested')):
            result = {**result, 'state': 'stopping' if control['desired'] == 'draining' else 'starting',
                'reason': 'SUPERVISOR_PENDING', 'next_action': 'Observe the same scheduled task; no detached process was launched.'}
        elif result['state'] == 'stopped' and control['desired'] == 'draining':
            drained = control.get('generation') is None or self.shutdown_receipt(control.get('generation')) == 'DRAINED'
            result = {**result, 'shutdown_outcome': 'drained' if drained else 'unconfirmed',
                'reason': 'SHUTDOWN_COMPLETE' if drained else 'SHUTDOWN_OUTCOME_UNCONFIRMED'}
        return result

    def _inspect_process(self, *, timeout=2.0):
        result = inspect_local_server(home=self.home, database=self.database,
            host=self.host, port=self.port, timeout=timeout)
        if result['state'] != 'stopped':
            return result
        try:
            receipt = read_json(self.home / LAUNCH_NAME)
        except FileNotFoundError:
            return result
        except (ValueError, OSError):
            return {**result, 'state': 'unknown', 'reason': 'LAUNCH_RECEIPT_UNAVAILABLE',
                'next_action': 'Inspect the retained launch receipt before retrying.'}
        if receipt.get('state') == 'pending':
            result = {**result, 'launch_recovery': {'receipt_revision': document_revision(receipt),
                'state': 'pending', 'action': 'recover-start'}}
            if process_exited(receipt.get('pid')) is True:
                return {**result, 'state': 'failed', 'reason': 'STARTUP_EXITED',
                    'next_action': 'Inspect startup diagnostics, then explicitly start again.'}
            return {**result, 'state': 'starting', 'reason': 'STARTUP_PENDING',
                'next_action': 'Observe this launch, or explicitly recover-start with its receipt revision if the launcher was interrupted.'}
        if receipt.get('state') == 'aborted_before_bootstrap':
            return {**result, 'reason': 'STARTUP_ABORTED',
                'launch_recovery': {'receipt_revision': receipt.get('recovered_from'), 'state': receipt['state']},
                'next_action': 'The pending launch was fenced. Start explicitly when ready; runtime work was not changed.'}
        if receipt.get('state') == 'failed':
            return {**result, 'state': 'failed', 'reason': receipt.get('reason', 'STARTUP_FAILED'),
                'next_action': 'Inspect startup diagnostics, then explicitly start again.'}
        return result

    def recover_start(self, *, expected_revision):
        """Fence one reviewed pending selection before its child can bootstrap."""
        base = inspect_local_server(home=self.home, database=self.database,
            host=self.host, port=self.port, timeout=.2)
        def refused(reason, action):
            state = 'unknown' if base['state'] == 'stopped' and reason in {
                'RECOVERY_OWNER_UNCONFIRMED', 'LAUNCH_REVISION_CONFLICT'} else base['state']
            return {**base, 'state': state, 'recovered': False, 'reason': reason, 'next_action': action}
        if not isinstance(expected_revision, str) or len(expected_revision) != 64 or any(
                char not in '0123456789abcdef' for char in expected_revision):
            return refused('INVALID_LAUNCH_REVISION', 'Use the receipt_revision returned by service status --json.')
        if not (self.home / LAUNCH_NAME).exists():
            return refused('NO_PENDING_LAUNCH', 'No retained detached launch exists for this instance.')
        try:
            with launch_exclusion(self.home, self.database), ExitStack() as owners:
                try:
                    context = read_json(self.home / CONTEXT_NAME)
                except FileNotFoundError:
                    context = {}
                if context.get('upgrade_pending'):
                    return refused('SERVICE_UPGRADE_PENDING', 'Resume the retained upgrade before launch recovery.')
                if (self.home / INSTALLATION_NAME).exists():
                    return refused('RECOVERY_REQUIRES_DETACHED', 'Use the selected user-service lifecycle; its task was not changed.')
                if base['state'] != 'stopped':
                    return refused('RECOVERY_OWNER_UNCONFIRMED', 'Inspect the current owner; recovery never stops a process.')
                # Hold lifetime and launch exclusions until the old child token
                # is fenced. A delayed child checks this receipt before bootstrap.
                for path in sorted({self.home / 'nexus.serve.guard',
                        self.database.with_name(self.database.name + '.serve.guard')}):
                    lock = ExclusiveFileLock(path)
                    lock.acquire()
                    owners.callback(lock.release)
                receipt = read_json(self.home / LAUNCH_NAME)
                if (receipt.get('revision') != 1 or receipt.get('instance_id') != base['instance_id']
                        or not isinstance(receipt.get('token'), str) or not receipt['token']):
                    return refused('INVALID_LAUNCH_RECEIPT', 'Inspect the retained launch receipt; it was preserved.')
                if receipt.get('state') == 'aborted_before_bootstrap':
                    original = {key: value for key, value in receipt.items() if key != 'recovered_from'}
                    original['state'] = 'pending'
                    confirmed = receipt.get('recovered_from') == expected_revision and document_revision(original) == expected_revision
                    if not confirmed:
                        return refused('LAUNCH_REVISION_CONFLICT', 'The retained launch changed; inspect status again.')
                    changed = False
                elif receipt.get('state') != 'pending' or 'recovered_from' in receipt:
                    return refused('RECOVERY_REQUIRES_PENDING', 'This launch already crossed bootstrap or terminated; use canonical lifecycle recovery.')
                elif document_revision(receipt) != expected_revision:
                    return refused('LAUNCH_REVISION_CONFLICT', 'The retained launch changed; inspect status again.')
                else:
                    atomic_json(self.home / LAUNCH_NAME, {**receipt, 'state': 'aborted_before_bootstrap',
                        'recovered_from': expected_revision})
                    changed = True
                return {**base, 'recovered': True, 'changed': changed, 'reason': 'STARTUP_ABORTED',
                    'launch_recovery': {'receipt_revision': expected_revision, 'state': 'aborted_before_bootstrap'},
                    'next_action': 'Start explicitly when ready. No process was started/stopped and runtime state was not changed.'}
        except LockBusy:
            return refused('RECOVERY_OWNER_UNCONFIRMED', 'A launch or process owns the instance; observe it before recovery.')
        except (OSError, ValueError):
            return {**refused('RECOVERY_UNCONFIRMED', 'Inspect the retained receipt and repeat with the same revision to confirm.'),
                'state': 'unknown'}
    def start(self):
        self.home.mkdir(parents=True, exist_ok=True)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        try:
            with launch_exclusion(self.home, self.database):
                result = self.inspect(timeout=.2, _launch_owned=True)
                if result['state'] != 'stopped' and result.get('reason') not in {
                        'STARTUP_EXITED', 'STARTUP_FAILED', 'SPAWN_FAILED'}:
                    return result
                if os.name == 'nt' or (self.home / INSTALLATION_NAME).exists():
                    try:
                        if self.installation.start():
                            return {**result, 'state': 'starting', 'supervisor': SUPERVISOR,
                                'reason': 'SUPERVISOR_PENDING', 'next_action': 'Observe this scheduled foreground task.'}
                    except (OSError, ValueError, ImportError) as error:
                        return installation_failure(result, error)
                context = validate_context(self.context)
                atomic_json(self.home / CONTEXT_NAME, context)
                receipt = {'revision': 1, 'instance_id': result['instance_id'],
                    'token': secrets.token_hex(16), 'state': 'pending', 'pid': None,
                    'requested_at': time.time()}
                atomic_json(self.home / LAUNCH_NAME, receipt)
                command = [context['executable'], '-m',
                    'okto_nexus.adapters.inbound.cli.service_process',
                    str(self.home), str(self.database), receipt['token']]
                options = {'creationflags': subprocess.DETACHED_PROCESS |
                           subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
                           } if os.name == 'nt' else {'start_new_session': True}
                try:
                    # No terminal handles, shell interpolation or provider secrets.
                    process = subprocess.Popen(command, cwd=context['cwd'], env=context['environment'],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, close_fds=True, **options)
                except OSError:
                    atomic_json(self.home / LAUNCH_NAME, {**receipt, 'state': 'failed', 'reason': 'SPAWN_FAILED'})
                    return {**result, 'state': 'failed', 'reason': 'SPAWN_FAILED',
                        'next_action': 'Check the executable, environment and OS detachment policy.'}
                atomic_json(self.home / LAUNCH_NAME, {**receipt, 'pid': process.pid})
                return {**result, 'state': 'starting', 'reason': 'STARTUP_PENDING',
                    'next_action': 'Observe this same launch; waiting does not start another process.'}
        except LockBusy:
            return {**self.inspect(timeout=.2), 'state': 'starting', 'reason': 'CONCURRENT_START',
                'next_action': 'Wait for the initialization already being selected.'}

    def request_stop(self, current, *, timeout, force=False):
        if type(force) is not bool:
            raise ValueError('Force must be a boolean.')
        pending = current.get('reason') in {'SUPERVISOR_PENDING', 'SUPERVISOR_LAST_ATTEMPT_FAILED'} and not current.get('generation')
        if force:
            actual = self._inspect_process(timeout=min(.5, timeout))
            if (not current.get('generation') or actual.get('generation') != current['generation']
                    or actual.get('instance_id') != current.get('instance_id')):
                return {**actual, 'state': 'failed', 'reason': 'INSTANCE_CHANGED',
                    'next_action': 'Inspect the current generation; no force was requested.'}
        if current['state'] not in {'ready', 'stopping'} and not pending:
            return current
        if (self.home / INSTALLATION_NAME).exists():
            try:
                with launch_exclusion(self.home, self.database):
                    actual = self._inspect_process(timeout=min(.5, timeout))
                    if (actual.get('generation') != current.get('generation')
                            or (pending and actual['state'] != 'stopped')):
                        return {**actual, 'state': 'failed', 'reason': 'INSTANCE_CHANGED',
                            'next_action': 'Observe the current generation before requesting another stop.'}
                    self.installation.begin_stop(current.get('generation'))
                    if pending:
                        return {**current, 'state': 'stopping', 'shutdown': {'state': 'DRAINED', 'resources': []},
                            'reason': 'STARTUP_SUPPRESSED', 'next_action': 'Wait for the scheduled entry to observe the stop latch and exit.'}
            except LockBusy:
                return {**current, 'reason': 'CONCURRENT_LIFECYCLE',
                    'next_action': 'Repeat stop after the current lifecycle operation completes.'}
            except (OSError, ValueError, ImportError) as error:
                return installation_failure(current, error)
        address = '[::1]' if self.host in {'::', '::1'} else '127.0.0.1'
        body = {'instance_id': current['instance_id'],
                'generation': current['generation'], 'timeout_seconds': float(timeout)}
        if force:
            body['force'] = True
        request = Request(f'http://{address}:{self.port}/api/v1/service/stop',
            data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=max(.01, timeout)) as response:
                raw = response.read(32769)
                if len(raw) > 32768:
                    raise ValueError('Oversized shutdown response')
                result = json.loads(raw)
                data = result['data']
                if (result.get('ok') is not True or data['instance_id'] != current['instance_id']
                        or data['generation'] != current['generation']):
                    raise ValueError('Shutdown identity mismatch')
                report = data['shutdown']
        except HTTPError as error:
            # An explicit canonical refusal is not a lost response. Never
            # print peer text, malformed bodies or URLs from an exception.
            reason = None
            try:
                raw = error.read(32769)
                if len(raw) <= 32768:
                    envelope = json.loads(raw)
                    refusal = envelope.get('error', {})
                    code = refusal.get('code')
                    details = refusal.get('details') or {}
                    if error.code in {400, 401, 403, 409, 422} and code in {
                            'CONFLICT', 'INSTANCE_MISMATCH', 'AUTH_FAILED', 'PERMISSION_DENIED',
                            'VALIDATION_ERROR', 'INVALID_TRANSITION'}:
                        reason = ('DRAIN_DECISION_NOT_AVAILABLE'
                            if details.get('reason') == 'DRAIN_DECISION_NOT_AVAILABLE'
                            else 'SHUTDOWN_REQUEST_REFUSED')
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            if reason:
                return {**current, 'state': 'failed', 'reason': reason,
                        'next_action': 'Inspect the current drain before another explicit decision.'}
            report = {'state': 'UNCONFIRMED', 'resources': []}
        except (OSError, ValueError, KeyError, TypeError):
            report = {'state': 'UNCONFIRMED', 'resources': []}
        return {**current, 'state': 'stopping', 'shutdown': report,
            'reason': 'RUNTIME_DRAINING', 'next_action': (
                'Observe the same generation; a force decision was submitted and its outcome must be confirmed.' if force else
                'Observe the same generation; no force or restart was requested.')}

    def shutdown_receipt(self, generation):
        try:
            receipt = read_json(self.home / 'service-shutdown.json')
        except (OSError, ValueError):
            return None
        return receipt.get('state') if receipt.get('generation') == generation else None

    def prepare_install(self):
        result = self._inspect_process(timeout=.2)
        try:
            self.installation.prepare(self.context)
            receipt = self.installation.receipt()
            if receipt and receipt['state'] == 'installed':
                return {**self.inspect(timeout=.2), 'installation_prepared': True,
                    'installation_state': 'installed'}
        except (OSError, ValueError, ImportError) as error:
            return installation_failure(result, error)
        return {**result, 'installation_prepared': True}

    def set_user_service_enabled(self, enabled):
        result = self._inspect_process(timeout=.2)
        try:
            if not self.home.exists():
                raise InstallationError('USER_SERVICE_NOT_INSTALLED', 'Install the selected integration first.')
            with launch_exclusion(self.home, self.database):
                changed = self.installation.set_enabled(enabled)
                return {**result, **changed, 'enablement_confirmed': True,
                    'installation_state': 'installed', 'supervisor': SUPERVISOR,
                    'next_action': ('Use service start for immediate execution.' if enabled else
                                    'Future task starts are disabled. Use service stop for canonical drain of a running instance.')}
        except LockBusy:
            return {**result, 'reason': 'CONCURRENT_LIFECYCLE', 'enablement_confirmed': False,
                'next_action': 'Repeat this operation after the current lifecycle operation completes.'}
        except (OSError, ValueError, ImportError) as error:
            return installation_failure(result, error)

    def install_user_service(self):
        self.home.mkdir(parents=True, exist_ok=True)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        try:
            with launch_exclusion(self.home, self.database):
                result = self._inspect_process(timeout=.2)
                if result['state'] != 'stopped' and result.get('reason') not in {'STARTUP_EXITED', 'STARTUP_FAILED', 'SPAWN_FAILED'}:
                    return {**result, 'reason': 'INSTALL_REQUIRES_STOP',
                        'next_action': 'Wait for controlled shutdown before changing the supervisor.'}
                receipt = self.installation.install(self.context)
                (self.home / LAUNCH_NAME).unlink(missing_ok=True)
                return {**result, 'state': 'stopped', 'reason': 'USER_SERVICE_INSTALLED',
                    'supervisor': SUPERVISOR, 'installation_state': receipt['state'],
                    'next_action': 'Start this instance with service start, or wait for the next user login.'}
        except LockBusy:
            return {**self.inspect(timeout=.2), 'state': 'starting', 'reason': 'CONCURRENT_LIFECYCLE',
                'next_action': 'Repeat install after the current lifecycle operation completes.'}
        except (OSError, ValueError, ImportError) as error:
            return installation_failure(self._inspect_process(timeout=.2), error)

    def uninstall_user_service(self):
        if not self.home.exists():
            try:
                self.installation.uninstall()
                return {**self.inspect(timeout=.2), 'installation_state': 'absent'}
            except (OSError, ValueError, ImportError) as error:
                return installation_failure(self._inspect_process(timeout=.2), error)
        try:
            with launch_exclusion(self.home, self.database):
                result = self._inspect_process(timeout=.2)
                if result['state'] != 'stopped':
                    return {**result, 'reason': 'UNINSTALL_REQUIRES_STOP',
                        'next_action': 'Wait for confirmed application shutdown before removing the integration.'}
                self.installation.uninstall()
                return {**result, 'installation_state': 'absent', 'reason': 'USER_SERVICE_REMOVED',
                    'next_action': 'Data and credentials are retained. Foreground or detached start remains available.'}
        except LockBusy:
            return {**self.inspect(timeout=.2), 'state': 'starting', 'reason': 'CONCURRENT_LIFECYCLE',
                'next_action': 'Repeat uninstall after the current lifecycle operation completes.'}
        except (OSError, ValueError, ImportError) as error:
            return installation_failure(self._inspect_process(timeout=.2), error)
