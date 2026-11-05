"""Short-lived lifecycle adapter; the foreground Server owns its own lifetime."""
from __future__ import annotations

from contextlib import contextmanager
import os
import json
from pathlib import Path
import secrets
import subprocess
import time
from urllib.request import ProxyHandler, Request, build_opener

from ..process_liveness import process_exited
from .context import CONTEXT_NAME, atomic_json, read_json, validate_context
from .inspection import NoRedirect, _held, inspect_local_server
from .locking import ExclusiveFileLock, LockBusy
from .installation import (INSTALLATION_NAME, SUPERVISOR,
                           ServerInstallation, installation_failure)

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

    def inspect(self, *, timeout=2.0, _launch_owned=False):
        result = self._inspect_process(timeout=timeout)
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
            'last_result': task.last_result, 'start_at_login': True,
            'available_before_login': False, 'available_after_logout': False,
            'definition_digest': receipt['native_digest']}}
        if result['state'] in {'ready', 'stopping'} and result.get('generation'):
            if actual_supervisor != SUPERVISOR:
                return {**result, 'state': 'failed', 'reason': 'SUPERVISOR_MISMATCH',
                    'next_action': 'The current owner is outside the installed task; reconcile the selected supervisor.'}
            if control['desired'] == 'draining':
                result = {**result, 'state': 'stopping', 'reason': 'RUNTIME_DRAINING',
                    'next_action': 'Repeat stop to observe this drain; start cannot reopen admission.'}
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
            if process_exited(receipt.get('pid')) is True:
                return {**result, 'state': 'failed', 'reason': 'STARTUP_EXITED',
                    'next_action': 'Inspect startup diagnostics, then explicitly start again.'}
            return {**result, 'state': 'starting', 'reason': 'STARTUP_PENDING',
                'next_action': 'Observe this same launch; waiting does not start another process.'}
        if receipt.get('state') == 'failed':
            return {**result, 'state': 'failed', 'reason': receipt.get('reason', 'STARTUP_FAILED'),
                'next_action': 'Inspect startup diagnostics, then explicitly start again.'}
        return result

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

    def request_stop(self, current, *, timeout):
        pending = current.get('reason') == 'SUPERVISOR_PENDING' and not current.get('generation')
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
        request = Request(f'http://{address}:{self.port}/api/v1/service/stop',
            data=json.dumps({'instance_id': current['instance_id'],
                'generation': current['generation'], 'timeout_seconds': float(timeout)}).encode(),
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
        except (OSError, ValueError, KeyError, TypeError):
            report = {'state': 'UNCONFIRMED', 'resources': []}
        return {**current, 'state': 'stopping', 'shutdown': report,
            'reason': 'RUNTIME_DRAINING', 'next_action': 'Observe the same generation; no force or restart was requested.'}

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
