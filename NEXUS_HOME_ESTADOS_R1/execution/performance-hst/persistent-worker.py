"""Prepared persistent-ASGI counterpart; requires a new Root window."""
import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hst_persistent_original', HERE / 'benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = benchmark
spec.loader.exec_module(benchmark)
REPO = benchmark.REPO
sha, schema, load, trace, productive, stats = (getattr(benchmark, n) for n in ('sha','schema','load','trace','productive','stats'))

@contextmanager
def guarded():
    popen, connect, connect_ex, socketpair, sendto = (
        subprocess.Popen, socket.socket.connect, socket.socket.connect_ex, socket.socketpair, socket.socket.sendto)
    local = threading.local()

    def forbidden(*args, **kwargs):
        raise RuntimeError('External process/network effects are prohibited in this measurement worker.')

    class ForbiddenProcess(popen):
        def __init__(self, *args, **kwargs):
            forbidden()

    def pair(*args, **kwargs):
        depth = getattr(local, 'depth', 0)
        local.depth = depth + 1
        try:
            return socketpair(*args, **kwargs)
        finally:
            local.depth = depth

    def permitted(address):
        return (getattr(local, 'depth', 0) > 0 and isinstance(address, tuple)
                and address[0] in ('127.0.0.1', '::1'))

    def scoped_connect(sock, address):
        if permitted(address):
            return connect(sock, address)
        forbidden()

    def scoped_connect_ex(sock, address):
        if permitted(address):
            return connect_ex(sock, address)
        forbidden()

    subprocess.Popen = ForbiddenProcess
    socket.socket.connect, socket.socket.connect_ex = scoped_connect, scoped_connect_ex
    socket.socketpair, socket.socket.sendto = pair, forbidden
    try:
        yield
    finally:
        subprocess.Popen = popen
        socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
        socket.socketpair, socket.socket.sendto = socketpair, sendto

async def persistent_measure(args, ready):
    manifest = json.loads(Path(args.dataset).read_text(encoding='utf-8'))
    if any(sha(REPO / path) != value for path, value in manifest['helper_source_pins'].items()):
        raise RuntimeError('Prepared fixture/helper source bytes changed between variants.')
    case = next(case for case in manifest['cases'] if case['size'] == args.connections)
    owned = Path(args.dataset).resolve().parent
    marker = json.loads((owned / '.hst-owned.json').read_text(encoding='utf-8'))
    if marker != dict(root=str(owned), kind='hst-performance-synthetic-only'):
        raise RuntimeError('Dataset ownership marker does not match its root.')
    home = Path(case['clones'][args.variant]).resolve()
    if not home.is_relative_to(owned) or not args.output.resolve().is_relative_to(owned):
        raise RuntimeError('Home/output escaped the explicitly owned benchmark root.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    db = home / case['db_relative']
    if sha(db) != case['database_sha256'] or schema(db) != case['schema_sha256']:
        raise RuntimeError('Dataset clone has already changed; never benchmark a reused clone.')
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app
    from httpx import AsyncClient, ASGITransport
    fixtures = load('hst_perf_clock_only', REPO / 'NEXUS_UI_R1/execution/fixtures.py')
    deps = bootstrap({}, ['--home', str(home), '--embedding-mode', 'off'])
    deps.clock = fixtures.ControlledClock(manifest['clock'])
    deps.config.feature_attention = deps.config.feature_observations = deps.config.feature_hitl = True
    app = build_app(deps)
    if schema(db) != case['schema_sha256']:
        raise RuntimeError('Bootstrap changed schema; review comparison compatibility.')
    client = AsyncClient(transport=ASGITransport(app, client=('127.0.0.1',65123)), base_url='http://hst-own.invalid')  # no lifespan/network
    version = 2 if args.variant == 'candidate-v2' else 1
    params = dict(workspace_id='hst-perf', limit=10, preview=3)
    if args.variant != 'baseline-v1':
        params['presentation_version'] = version
    base = '/api/v1/home/harness-board'
    result = dict(version=1, variant=args.variant, connections=args.connections, volume=case['volume'],
        environment=dict(python=sys.version, sqlite=sqlite3.sqlite_version, platform=platform.platform(),
                         cpu_count=os.cpu_count(), transport='httpx AsyncClient/ASGITransport, one persistent asyncio loop; no TCP/browser/lifespan'), series={})
    deadline = time.monotonic() + args.max_seconds

    async def read(path):
        started = time.perf_counter()
        response = await client.get(path, params=params)
        elapsed = (time.perf_counter() - started) * 1000
        payload = response.json().get('data', {})
        metric = dict(elapsed_ms=elapsed, http_status=response.status_code, status=payload.get('status'),
            source_status=payload.get('source_status'), payload_bytes=len(response.content),
            revision=payload.get('revision'), next_refresh_at=payload.get('next_refresh_at'))
        return payload, metric
    before = productive(deps.connection_factory)
    try:
        first, metric = await read(base)
        result['first_http_response'] = metric
        cards = [item for lane in first.get('columns', {}).values() for item in lane['items'] if item['kind'] == 'harness']
        paths = {'overview_refresh': base}
        if cards:
            paths['activity_page'] = base + '/cards/' + cards[0]['id'] + '/children'
        for name, path in paths.items():
            for _ in range(args.warmup):
                if time.monotonic() >= deadline:
                    break
                await read(path)
            with trace(deps.connection_factory) as instrument:
                await read(path)
            result.setdefault('instrumentation', {})[name] = dict(instrument,
                statement_count=sum(instrument['opcodes'].values()), stored_sql=False, stored_parameters=False)
            samples = []
            for _ in range(args.samples):
                if time.monotonic() >= deadline:
                    break
                _, sample = await read(path)
                samples.append(sample)
            result['series'][name] = stats(samples)
        result['productive_drift'] = [name for name, value in productive(deps.connection_factory).items() if value != before[name]]
        valid = not result['productive_drift'] and all(series['count'] == args.samples and all(
            sample['http_status'] == 200 and sample['status'] == 'ready' for sample in series['samples'])
            for series in result['series'].values()) and len(result['series']) == 2
        result['status'] = 'MEASURED' if valid else 'NOT_QUALIFIED'
        result['targets'] = dict(read_p95_ms=500, http_first_response_proxy_ms=2000,
            read_target_met=valid and all(series['nearest_rank_p95_ms'] <= 500 for series in result['series'].values()),
            first_http_proxy_met=valid and metric['elapsed_ms'] <= 2000,
            first_useful_dom=dict(status='NOT_RUN', target_ms=2000, reason='Not measured by an ASGI HTTP runner.'))
        result['schema_after'] = schema(db)
    finally:
        await client.aclose()
        deps.connection_factory.close()
    return result

def measure(args, ready):
    result = asyncio.run(persistent_measure(args, ready))
    result['counterpart'] = dict(original_runner_sha256=sha(HERE/'benchmark.py'), original_guard_sha256=sha(HERE/'measure-worker.py'),
        persistent_worker_sha256=sha(__file__), interpretation='Transport/lifecycle counterpart; preserves original TestClient cuts. Not browser DOM/network latency.')
    return result

if __name__ == '__main__':
    if len(sys.argv)<2 or sys.argv[1]!='measure':
        raise RuntimeError('Measurement only: never rebuild original datasets.')
    benchmark.no_external_effects = guarded
    benchmark.measure = measure
    benchmark.main()
