"""Foreground scheduled-task entry, fenced by the selected host installation.

No child daemon/supervisor is created. A durable explicit-stop latch suppresses
failure recovery while the canonical drain is in progress, including a crash
or loss of the CLI response during that drain.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from ...outbound.service_manager.context import CONTEXT_NAME, atomic_json, read_json, validate_context
from ...outbound.service_manager.installation import CONTROL_NAME, ServerInstallation, SUPERVISOR, context_digest
from ...outbound.service_manager.identity import windows_logon_session
from ...outbound.service_manager.local import launch_exclusion
from ...outbound.service_manager.locking import LockBusy


def run(home: Path, database: Path, token: str, *, installation=None, supervisor_cycle=None,
        supervisor_nonce=None) -> int:
    from ..http.lock import ServeLock
    installation = installation or ServerInstallation(home, database)
    if supervisor_cycle is not None:
        from ...outbound.service_manager.supervision import join_parent
        try:
            if not join_parent(home, database, installation, token, supervisor_cycle, supervisor_nonce):
                return 0  # stop acknowledged identities, without runtime bootstrap
        except (OSError, ValueError):
            return 2
    lock = ServeLock(home, db_path=database)
    deadline = time.monotonic() + 30
    while True:
        try:
            with launch_exclusion(home, database):
                receipt = installation.receipt()
                if not receipt or receipt['token'] != token or receipt['state'] != 'installed':
                    return 2
                control = installation.control(receipt)
                if supervisor_cycle is not None:
                    from ...outbound.service_manager.supervision import validate_child, own_birth
                    validate_child(home, receipt, installation.instance_id,
                                   supervisor_cycle, os.getpid(), own_birth(), supervisor_nonce)
                    if control.get('cycle_id') != supervisor_cycle:
                        return 2
                logon = windows_logon_session()
                if control['desired'] == 'draining' and control.get('logon_session') == logon:
                    return 0  # intentional stop, never a failed runtime attempt
                # Correlate the current native definition before touching DB.
                _, task = installation.observe(check_context=False)
                if not task.enabled:
                    return 0  # a queued login cannot bootstrap after disable
                context = validate_context(read_json(home / CONTEXT_NAME))
                if context_digest(context) != receipt['context_digest']:
                    return 2
                lock.acquire()
                atomic_json(home / CONTROL_NAME, {**control, 'revision': 1, 'token': token,
                    'desired': 'running', 'launch_requested': False, 'logon_session': logon})
                break
        except LockBusy:
            if time.monotonic() >= deadline:
                return 3
            time.sleep(.05)
        except (OSError, ValueError):
            return 2
    previous_environment, previous_cwd = dict(os.environ), Path.cwd()
    previous_streams = sys.stdin, sys.stdout, sys.stderr
    streams = []
    try:
        # pythonw has None streams. Do not persist arbitrary provider/HTTP text
        # as lifecycle logs; retain only bounded coded startup diagnostics here.
        for name in ('stdin', 'stdout', 'stderr'):
            if getattr(sys, name) is None:
                stream = open(os.devnull, 'r' if name == 'stdin' else 'w', encoding='utf-8')
                streams.append(stream)
                setattr(sys, name, stream)
        os.environ.clear()
        os.environ.update(context['environment'])
        os.chdir(context['cwd'])
        from .serve import run_serve
        code = run_serve(context['arguments'], context['environment'],
                         acquired_lock=lock, supervisor=SUPERVISOR,
                         settings_pinned_fields=context.get('settings_pinned_fields'),
                         settings_provenance_legacy=context.get('settings_provenance_legacy', False))
    except (Exception, SystemExit):
        code = 1
    finally:
        # Keep the generation and runtime receipt even on nonzero exit. Work
        # uncertainty belongs to canonical reconciliation, never the task code.
        try:
            atomic_json(home / 'service-supervisor-exit.json', {'revision': 1,
                'generation': lock.generation, 'exit_code': locals().get('code', 1)})
        except OSError:
            pass
        lock.release()
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_environment)
        sys.stdin, sys.stdout, sys.stderr = previous_streams
        for stream in streams:
            stream.close()
    try:
        if installation.control(receipt)['desired'] == 'draining':
            return 0
    except (OSError, ValueError):
        pass
    return code


if __name__ == '__main__':
    cycle = nonce = None
    if len(sys.argv) == 8 and sys.argv[4] == '--supervisor-cycle' and sys.argv[6] == '--supervisor-nonce':
        cycle, nonce = sys.argv[5], sys.argv[7]
    if len(sys.argv) not in {4, 8} or (len(sys.argv) == 8 and cycle is None):
        raise SystemExit(2)
    raise SystemExit(run(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3],
                        supervisor_cycle=cycle, supervisor_nonce=nonce))
