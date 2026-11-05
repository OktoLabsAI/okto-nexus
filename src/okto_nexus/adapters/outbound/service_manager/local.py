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
from .inspection import NoRedirect, inspect_local_server
from .locking import ExclusiveFileLock, LockBusy

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
    def __init__(self, *, home, database, host, port, context=None):
        self.home, self.database = Path(home).resolve(), Path(database).resolve()
        self.host, self.port, self.context = host, port, context

    def inspect(self, *, timeout=2.0):
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
                result = self.inspect(timeout=.2)
                if result['state'] != 'stopped' and result.get('reason') not in {
                        'STARTUP_EXITED', 'STARTUP_FAILED', 'SPAWN_FAILED'}:
                    return result
                if (self.home / 'service-installation.json').exists():
                    return {**result, 'state': 'failed', 'reason': 'SUPERVISOR_REQUIRED',
                        'next_action': 'Use the installed supervisor; detached fallback is disabled.'}
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
        if current['state'] not in {'ready', 'stopping'}:
            return current
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
