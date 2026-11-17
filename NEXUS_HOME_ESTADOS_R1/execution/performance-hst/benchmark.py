"""Prepared installed workers. Do not run before PACKAGE_READY/exclusive window."""
from contextlib import contextmanager
import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import zipfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
NOW = '2026-11-16T12:00:00.000000Z'
PACKAGES = ('okto_nexus', 'nexus_connector_core', 'okto_nexus_connector')


def sanitize_environment():
    """Worker-local allowlist, before any product/test helper import."""
    env_home = Path(tempfile.mkdtemp(prefix='nexus-hst-performance-env-')).resolve()
    inherited = {key: value for key, value in os.environ.items() if key.upper() in
        {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT'}}
    system = Path(inherited.get('SYSTEMROOT', 'C:/Windows'))
    os.environ.clear()
    os.environ.update(inherited)
    for key, relative in (('HOME', 'profile'), ('USERPROFILE', 'profile'), ('APPDATA', 'roaming'),
                          ('LOCALAPPDATA', 'local'), ('TMP', 'temp'), ('TEMP', 'temp')):
        directory = env_home / relative
        directory.mkdir(exist_ok=True)
        os.environ[key] = str(directory)
    os.environ.update(PATH=os.pathsep.join((str(system / 'System32'), str(system), str(Path(sys.executable).parent))),
        CODEX_HOME=str(env_home / 'missing-codex'), CLAUDE_CONFIG_DIR=str(env_home / 'missing-claude'),
        PI_CODING_AGENT_DIR=str(env_home / 'missing-pi'), PYTHONDONTWRITEBYTECODE='1')
    return env_home


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    if path.exists():
        raise RuntimeError('Refusing to overwrite previous evidence: ' + str(path))
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def schema(db):
    with sqlite3.connect(db) as conn:
        rows = list(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"))
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def payload(ready):
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise RuntimeError('Worker requires installed Python -I -B.')
    if Path(sys.executable).resolve() != Path(ready['python']).resolve() or not ready.get('ready'):
        raise RuntimeError('Selected frozen prefix does not match READY.')
    if sha(ready['wheel']) != ready['wheel_sha256']:
        raise RuntimeError('Wheel identity changed.')
    result = {}
    prefix = Path(sys.prefix).resolve()
    for name in PACKAGES:
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve()
        if not origin.is_relative_to(prefix):
            raise RuntimeError('Checkout or foreign product import: ' + name)
        files = {p.relative_to(origin.parent).as_posix(): sha(p) for p in origin.parent.rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
        result[name] = dict(origin=str(origin), count=len(files), files=files)
    if sum(item['count'] for item in result.values()) != ready['payload_files']:
        raise RuntimeError('Installed package payload count differs from READY.')
    with zipfile.ZipFile(ready['wheel']) as wheel:
        nexus = result['okto_nexus']
        for item in wheel.infolist():
            if item.is_dir() or not item.filename.startswith('okto_nexus/'):
                continue
            relative = item.filename.removeprefix('okto_nexus/')
            if nexus['files'].get(relative) != hashlib.sha256(wheel.read(item)).hexdigest():
                raise RuntimeError('Installed Nexus bytes differ from frozen wheel.')
    return result


def origin_guard():
    prefix = Path(sys.prefix).resolve()
    for name, module in tuple(sys.modules.items()):
        if name.split('.')[0] not in PACKAGES or not getattr(module, '__file__', None):
            continue
        if not Path(module.__file__).resolve().is_relative_to(prefix):
            raise RuntimeError('A loaded product submodule escaped the selected prefix: ' + name)


@contextmanager
def no_external_effects():
    original_popen, original_connect = subprocess.Popen, socket.socket.connect

    def forbidden(*args, **kwargs):
        raise RuntimeError('No subprocess or network connection is allowed in this benchmark worker.')
    subprocess.Popen = forbidden
    socket.socket.connect = forbidden
    try:
        yield
    finally:
        subprocess.Popen, socket.socket.connect = original_popen, original_connect


def build(args, ready):
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    save(root / '.hst-owned.json', dict(root=str(root), kind='hst-performance-synthetic-only'))
    dataset = load('hst_perf_dataset', HERE / 'dataset.py')
    # Product is already imported/guarded before adding any fixture-helper path.
    fixtures = load('hst_perf_fixtures', REPO / 'NEXUS_UI_R1/execution/fixtures.py')
    manifest = dict(version=1, state='BUILDING', clock=NOW, ready=ready,
        fixture_sha256=sha(REPO / 'NEXUS_UI_R1/execution/fixtures.py'),
        builder_sha256=sha(HERE / 'dataset.py'), cases=[])
    for size in (1, 10, 100):
        own = root / ('seed-' + str(size))
        with fixtures.scenario(own, clock=fixtures.ControlledClock(NOW)) as s:
            s.fixtures_copy = fixtures._copy
            volume = dataset.seed(s, size, 100_000 if size == 100 else 0)
            source_home = Path(s.deps.config.home_dir).resolve()
            db_relative = Path(s.deps.config.db_path).resolve().relative_to(source_home)
        # The generator/lifespan/factory have exited; no live SQLite/WAL copy.
        initial_db = source_home / db_relative
        clones = {}
        for variant in ('baseline-v1', 'candidate-v1', 'candidate-v2'):
            target = root / ('case-' + str(size)) / variant
            shutil.copytree(source_home, target)
            if sha(target / db_relative) != sha(initial_db):
                raise RuntimeError('Clone is not byte-identical to its source DB.')
            clones[variant] = str(target)
        manifest['cases'].append(dict(size=size, volume=volume, db_relative=str(db_relative),
            database_sha256=sha(initial_db), schema_sha256=schema(initial_db), clones=clones))
        print(json.dumps(dict(phase='built', connections=size)), flush=True)
    manifest['state'] = 'BUILT_NOT_MEASURED'
    save(root / 'dataset.json', manifest)


@contextmanager
def trace(factory):
    original = factory.unit_of_work
    counts, uows, writes = {}, [], []
    lock = threading.Lock()

    @contextmanager
    def wrapped(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            c, before = uow.connection, uow.connection.total_changes
            with lock:
                uows.append(dict(write=kwargs.get('write', True)))

            def observed(statement):
                # Expanded SQL is ephemeral; retain only opcode counts.
                opcode = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else 'EMPTY'
                with lock:
                    counts[opcode] = counts.get(opcode, 0) + 1
            c.set_trace_callback(observed)
            try:
                yield uow
            finally:
                with lock:
                    writes.append(c.total_changes - before)
                c.set_trace_callback(None)
    factory.unit_of_work = wrapped
    report = dict(opcodes=counts, uows=uows, changes=writes)
    try:
        yield report
    finally:
        factory.unit_of_work = original


PRODUCTIVE = ('connection_setup_commits', 'execution_bindings', 'runtime_execution_grants',
    'handoffs', 'execution_sessions', 'execution_operations', 'execution_decisions',
    'execution_dispatch_outbox', 'delivery_outbox', 'runtime_handoff_bindings', 'approvals',
    'connection_authorization_receipts', 'execution_receipts', 'execution_native_requests')


def productive(factory):
    with factory.unit_of_work(write=False) as uow:
        return {name: hashlib.sha256(json.dumps(sorted(json.dumps(dict(row), sort_keys=True)
            for row in uow.connection.execute('SELECT * FROM ' + name)), separators=(',', ':')).encode()).hexdigest()
                for name in PRODUCTIVE}


def stats(samples):
    values = sorted(sample['elapsed_ms'] for sample in samples)
    return dict(samples=samples, count=len(values), p50_ms=statistics.median(values) if values else None,
        nearest_rank_p95_ms=values[math.ceil(.95 * len(values)) - 1] if values else None,
        max_payload_bytes=max((sample['payload_bytes'] for sample in samples), default=None))


def measure(args, ready):
    manifest = json.loads(Path(args.dataset).read_text(encoding='utf-8'))
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
    from fastapi.testclient import TestClient
    fixtures = load('hst_perf_clock_only', REPO / 'NEXUS_UI_R1/execution/fixtures.py')
    deps = bootstrap({}, ['--home', str(home), '--embedding-mode', 'off'])
    deps.clock = fixtures.ControlledClock(manifest['clock'])
    deps.config.feature_attention = deps.config.feature_observations = deps.config.feature_hitl = True
    app = build_app(deps)
    if schema(db) != case['schema_sha256']:
        raise RuntimeError('Bootstrap changed schema; review comparison compatibility.')
    client = TestClient(app, client=('127.0.0.1', 65123))  # no lifespan/native startup
    version = 2 if args.variant == 'candidate-v2' else 1
    params = dict(workspace_id='hst-perf', limit=10, preview=3)
    if args.variant != 'baseline-v1':
        params['presentation_version'] = version
    base = '/api/v1/home/harness-board'
    result = dict(version=1, variant=args.variant, connections=args.connections, volume=case['volume'],
        environment=dict(python=sys.version, sqlite=sqlite3.sqlite_version, platform=platform.platform(),
                         cpu_count=os.cpu_count(), transport='ASGI HTTP; no TCP/browser/lifespan'), series={})
    deadline = time.monotonic() + args.max_seconds

    def read(path):
        started = time.perf_counter()
        response = client.get(path, params=params)
        elapsed = (time.perf_counter() - started) * 1000
        payload = response.json().get('data', {})
        metric = dict(elapsed_ms=elapsed, http_status=response.status_code, status=payload.get('status'),
            source_status=payload.get('source_status'), payload_bytes=len(response.content),
            revision=payload.get('revision'), next_refresh_at=payload.get('next_refresh_at'))
        return payload, metric
    before = productive(deps.connection_factory)
    try:
        first, metric = read(base)
        result['first_http_response'] = metric
        cards = [item for lane in first.get('columns', {}).values() for item in lane['items'] if item['kind'] == 'harness']
        paths = {'overview_refresh': base}
        if cards:
            paths['activity_page'] = base + '/cards/' + cards[0]['id'] + '/children'
        for name, path in paths.items():
            for _ in range(args.warmup):
                if time.monotonic() >= deadline:
                    break
                read(path)
            with trace(deps.connection_factory) as instrument:
                read(path)
            result.setdefault('instrumentation', {})[name] = dict(instrument,
                statement_count=sum(instrument['opcodes'].values()), stored_sql=False, stored_parameters=False)
            samples = []
            for _ in range(args.samples):
                if time.monotonic() >= deadline:
                    break
                _, sample = read(path)
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
        client.close()
        deps.connection_factory.close()
    return result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('mode', choices=('build', 'measure'))
    parser.add_argument('--released', required=True, choices=('PACKAGE_READY',))
    parser.add_argument('--ready', type=Path, required=True)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--variant', choices=('baseline-v1', 'candidate-v1', 'candidate-v2'))
    parser.add_argument('--connections', type=int, choices=(1, 10, 100))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--warmup', type=int, default=3)
    parser.add_argument('--max-seconds', type=int, default=180)
    args = parser.parse_args()
    if args.samples < 20 or args.warmup < 3 or not 1 <= args.max_seconds <= 180:
        parser.error('Require >=20 measured samples, >=3 warmups and <=180s phase budget.')
    ready = json.loads(args.ready.read_text(encoding='utf-8'))
    temp_root = Path(tempfile.gettempdir()).resolve()
    task_root = args.root.resolve() if args.mode == 'build' and args.root else args.dataset.resolve().parent if args.dataset else None
    if (task_root is None or not task_root.is_relative_to(temp_root)
            or not task_root.name.startswith('nexus-hst-performance-')
            or not Path.cwd().resolve().is_relative_to(temp_root)):
        raise RuntimeError('Require a new named own Temp dataset root and a Temp working directory.')
    env_home = sanitize_environment()
    before = payload(ready)
    with no_external_effects():
        if args.mode == 'build':
            if args.root is None:
                parser.error('--root is required for build')
            build(args, ready)
        else:
            if not all((args.dataset, args.variant, args.connections, args.output)):
                parser.error('measure requires dataset/variant/connections/output')
            if args.output.exists():
                raise RuntimeError('Refusing to overwrite prior measurement.')
            result = measure(args, ready)
    origin_guard()
    after = payload(ready)
    if before != after:
        raise RuntimeError('Installed payload changed during benchmark.')
    if args.mode == 'measure':
        result.update(payload_files=sum(p['count'] for p in after.values()), payload_drift=False,
            package_modules={name: dict(origin=value['origin'], count=value['count']) for name, value in after.items()},
            wheel_sha256=ready['wheel_sha256'], source_candidate=ready['source_candidate'], runner_sha256=sha(__file__),
            own_environment_home=str(env_home))
        save(args.output, result)
        print(json.dumps(dict(variant=args.variant, connections=args.connections, status=result['status'])), flush=True)


if __name__ == '__main__':
    main()
