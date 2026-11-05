"""Detached entry into the existing foreground Server, with durable launch fencing."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from ...outbound.service_manager.context import CONTEXT_NAME, atomic_json, read_json, validate_context
from ...outbound.service_manager.local import LAUNCH_NAME, launch_exclusion
from ...outbound.service_manager.locking import LockBusy


def run(home: Path, database: Path, token: str) -> int:
    from ..http.lock import ServeLock
    lock = ServeLock(home, db_path=database)
    receipt_path = home / LAUNCH_NAME
    deadline = time.monotonic() + 30
    while True:
        try:
            with launch_exclusion(home, database):
                receipt = read_json(receipt_path)
                if receipt.get('token') != token or receipt.get('state') != 'pending':
                    return 2
                context = validate_context(read_json(home / CONTEXT_NAME))
                lock.acquire()
                atomic_json(receipt_path, {**receipt, 'state': 'owned', 'generation': lock.generation})
                break
        except LockBusy:
            if time.monotonic() >= deadline:
                return 3
            time.sleep(.05)
    try:
        from .serve import run_serve
        code = run_serve(context['arguments'], context['environment'],
                         acquired_lock=lock, supervisor='detached',
                         settings_pinned_fields=context.get('settings_pinned_fields'),
                         settings_provenance_legacy=context.get('settings_provenance_legacy', False))
        if code:
            atomic_json(receipt_path, {**receipt, 'state': 'failed', 'reason': 'STARTUP_FAILED'})
        return code
    except (Exception, SystemExit):
        atomic_json(receipt_path, {**receipt, 'state': 'failed', 'reason': 'STARTUP_FAILED'})
        return 1
    finally:
        lock.release()


if __name__ == '__main__':
    raise SystemExit(run(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]))
