"""PREPARED installed HTTP performance fixture. Never runs on import.

Requires a separate Root DOM window AFTER the final ASGI matrix. Own synthetic
seed only; no native/provider authority qualification and no lifespan startup.
"""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def serve(app, listener, control, public, max_seconds):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='warning', access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    started = time.monotonic()
    try:
        while not server.started:
            if task.done():
                await task
                raise RuntimeError('HTTP listener exited before READY')
            if time.monotonic() - started > 30:
                raise TimeoutError('HTTP startup deadline')
            await asyncio.sleep(.05)
        (control / 'ready.json').write_text(json.dumps(public, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'ready': True, 'public_ready': str(control / 'ready.json'), 'origin': public['origin']}), flush=True)
        while not (control / 'stop').exists() and not task.done():
            if time.monotonic() - started > max_seconds:
                raise TimeoutError('Owned DOM fixture deadline; preserve this failed cut')
            await asyncio.sleep(.1)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 15)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--window', required=True, choices=['PERF_DOM_WINDOW_OPEN'])
    parser.add_argument('--ready', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=180)
    args = parser.parse_args()
    assert 1 <= args.max_seconds <= 240
    # Loading these helpers imports no checkout application. Their frozen seed
    # pins remain authoritative; do not rewrite either helper for this fixture.
    benchmark = load('hst_large_dom_benchmark', HERE / 'benchmark.py')
    worker = load('hst_large_dom_guard', HERE / 'persistent-worker.py')
    ready = json.loads(args.ready.read_text(encoding='utf-8'))
    assert ready.get('ready') and ready.get('prefix_frozen')
    assert benchmark.sha(ready['wheel']) == ready['wheel_sha256']
    source = args.dataset.resolve()
    manifest = json.loads(source.read_text(encoding='utf-8'))
    assert manifest.get('workload') == 'J04-open-complement'
    owner = source.parent
    assert owner.name.startswith('nexus-hst-performance-')
    assert json.loads((owner / '.hst-owned.json').read_text()) == {
        'root': str(owner), 'kind': 'hst-performance-synthetic-only'}
    for name, expected in manifest['helper_source_pins'].items():
        assert benchmark.sha(REPO / name) == expected, 'Frozen helper source drift'
    case = next(c for c in manifest['cases'] if c['size'] == 100)
    assert case['volume']['actual_open'] == 1000 and case['volume']['actual_native_history'] == 100000
    seed = owner / 'seed-100-open/home'
    assert seed.resolve().is_relative_to(owner)
    assert benchmark.sha(seed / case['db_relative']) == case['database_sha256']
    assert benchmark.schema(seed / case['db_relative']) == case['schema_sha256']
    benchmark.sanitize_environment()
    before_payload = benchmark.payload(ready)  # Enforces -I -B and installed origins.
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-performance-large-dom-')).resolve()
    control = root / 'control'
    control.mkdir()
    home = root / 'home'
    shutil.copytree(seed, home)
    assert benchmark.sha(home / case['db_relative']) == case['database_sha256']
    (root / '.hst-owned.json').write_text(json.dumps({'root': str(root), 'kind': 'hst-large-dom-performance-only'}))
    events = []
    deps, listener, client = None, None, None
    before_productive = None
    error = None
    try:
        with worker.guarded():
            from fastapi.testclient import TestClient
            from okto_nexus.adapters.inbound.http.app import build_app
            from okto_nexus.bootstrap.dependencies import bootstrap
            import okto_nexus.adapters.inbound.http.app as app_module
            import os

            fixtures = load('hst_large_dom_clock', REPO / 'NEXUS_UI_R1/execution/fixtures.py')
            deps = bootstrap({}, ['--home', str(home), '--embedding-mode', 'off'])
            deps.clock = fixtures.ControlledClock(manifest['clock'])
            deps.config.feature_attention = deps.config.feature_observations = deps.config.feature_hitl = True
            app = build_app(deps)
            assert benchmark.schema(home / case['db_relative']) == case['schema_sha256'], 'Schema changed during bootstrap'
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(('127.0.0.1', 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            origin = f'http://127.0.0.1:{port}'
            # No context-manager entry: entering TestClient would run lifespan.
            client = TestClient(app, base_url=origin, client=('127.0.0.1', 65123))
            canonical = load('hst_large_dom_controls', HERE.parent / 'browser-hst/canonical_controls.py')
            controls = canonical.Controls(deps, app, client, root, {'workspace_id': 'hst-perf'}, record=events.append)
            controls.configure_browser_session()
            controls.write_private_storage(port)  # Cookie bytes remain own Temp.
            surface = load('hst_large_dom_surface', HERE.parent / 'browser-hst/browser_surface.py')
            public = {'ready': True, 'window': args.window, 'kind': 'HST_LARGE_DOM_PERFORMANCE_FIXTURE',
                'origin': origin, 'workspace_id': 'hst-perf', 'presentation_version': 2,
                'seed_clock': manifest['clock'], 'dataset_sha256': benchmark.sha(source),
                'seed_db_sha256': case['database_sha256'], 'clone_db_sha256_before_bootstrap': case['database_sha256'],
                'schema_sha256': case['schema_sha256'],
                'counts': {'registered_connections': 100, 'open_activities': 1000, 'native_events': 100000},
                'lifespan': 'off', 'payload_files': ready['payload_files'], 'wheel_sha256': ready['wheel_sha256'],
                'source_commit': ready.get('source_commit', ready.get('source_candidate')),
                'http_pid': os.getpid(), 'native_processes_started': 0, 'provider_calls': 0,
                'clock_provenance': 'Server ControlledClock from unchanged synthetic seed; browser Date-only override required; no real authority claim'}
            with deps.connection_factory.unit_of_work(write=False) as uow:
                conn = uow.connection
                public['server_id'] = conn.execute('SELECT server_id FROM execution_executors LIMIT 1').fetchone()[0]
                actual = {
                    'registered_connections': conn.execute('SELECT COUNT(*) FROM execution_bindings b '
                        'JOIN execution_workspace_bindings w USING(server_id,executor_id,workspace_binding_id) '
                        'WHERE w.workspace_id=?', ('hst-perf',)).fetchone()[0],
                    'open_activities': conn.execute("SELECT COUNT(*) FROM execution_operations WHERE workspace_id=? "
                        "AND action='turn.submit' AND admission_state='ACCEPTED'", ('hst-perf',)).fetchone()[0],
                    'native_events': conn.execute('SELECT COUNT(*) FROM execution_event_ingress '
                        'JOIN execution_sessions USING(server_id,executor_id,session_id) WHERE workspace_id=?',
                        ('hst-perf',)).fetchone()[0],
                }
                assert actual == public['counts'] and not conn.execute('PRAGMA foreign_key_check').fetchall(), 'Synthetic volume/schema qualification failed'
            static = Path(app_module.__file__).parent / 'static'
            public['assets'] = {p.name: benchmark.sha(p) for p in sorted((static / 'assets').glob('*')) if p.is_file()}
            public['index_sha256'] = benchmark.sha(static / 'index.html')
            before_productive = benchmark.productive(deps.connection_factory)
            asyncio.run(serve(surface.BrowserSurface(app, record=events.append), listener, control, public, args.max_seconds))
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        if client is not None:
            client.close()
        if listener is not None:
            listener.close()
        report = {'kind': 'HST_LARGE_DOM_PERFORMANCE_FIXTURE', 'error': error, 'http_requests': events,
                  'schema_unchanged': benchmark.schema(home / case['db_relative']) == case['schema_sha256'],
                  'source_dataset_unchanged': benchmark.sha(seed / case['db_relative']) == case['database_sha256'],
                  'auth_store_telemetry': 'Own canonical account/login/read audit only; private cookie never exported'}
        if deps is not None:
            after = benchmark.productive(deps.connection_factory)
            report['productive_drift'] = [k for k in after if before_productive is not None and after[k] != before_productive[k]]
            deps.connection_factory.close()
        benchmark.origin_guard()
        report['payload_drift'] = benchmark.payload(ready) != before_payload
        (control / 'final.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'exited': True, 'final': str(control / 'final.json'), 'error': error}), flush=True)


if __name__ == '__main__':
    main()
