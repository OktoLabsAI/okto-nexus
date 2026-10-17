"""One-off physical directory audit measurement for M4; not a CI regression.

Run with the installed Nexus wheel and source tests on PYTHONPATH. The script
uses an isolated migrated Server database and empty physical journal files;
it never contacts a real harness or the running Nexus installation.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / 'tests' / 'execution_r4'))
from test_local_session_catalog import catalog_fixture  # noqa: E402


async def measure(count: int) -> dict:
    build_root = (WORKSPACE / 'build' / 'm4d4f-directory-audit').resolve()
    build_root.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix=f'audit-{count}-', dir=build_root)).resolve()
    if not target.is_relative_to(build_root):
        raise RuntimeError('Audit fixture escaped the workspace build directory.')
    host = None
    try:
        started = time.perf_counter()
        catalog, factory, _ = catalog_fixture(target, count)
        host = catalog.owner.host
        await catalog.backfill()
        await host._ledger()
        for index in range(count):
            (host.store_dir / catalog._name(f'session-{index}')).touch()
        setup_seconds = time.perf_counter() - started
        batches = []
        steps = [0]
        def progress():
            steps[0] += 1
            return 0
        @contextmanager
        def measured_uow(*, write=False):
            with factory.unit_of_work(write=write) as uow:
                uow.connection.set_progress_handler(progress, 1)
                try:
                    yield uow
                finally:
                    uow.connection.set_progress_handler(None, 0)
        catalog.owner.factory = SimpleNamespace(unit_of_work=measured_uow)
        verify = catalog.verify_names
        def observe(names):
            batches.append(len(names))
            return verify(names)
        catalog.verify_names = observe
        started = time.perf_counter()
        present = await catalog.audit_files()
        audit_seconds = time.perf_counter() - started
        assert present and batches and max(batches) <= 128
        return {
            'entries': count, 'setup_seconds': round(setup_seconds, 3),
            'audit_seconds': round(audit_seconds, 3),
            'verification_batches': len(batches),
            'largest_batch': max(batches), 'sqlite_vm_steps': steps[0],
        }
    finally:
        if host is not None:
            await host.shutdown()
        if not target.is_relative_to(build_root):
            raise RuntimeError('Refusing cleanup outside the benchmark root.')
        shutil.rmtree(target)


async def main() -> None:
    counts = [int(value) for value in sys.argv[1:]] or [1_000, 10_000]
    if any(count < 1 or count > 100_000 for count in counts):
        raise ValueError('Benchmark counts must be between 1 and 100,000.')
    for count in counts:
        print(json.dumps(await measure(count), sort_keys=True), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
