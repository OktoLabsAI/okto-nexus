"""Two diagnostic GETs only: cProfile, then SQL/fetch/EXPLAIN. No product edit."""
from contextlib import contextmanager
import cProfile
import importlib.util
import json
from pathlib import Path
import pstats
import shutil
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


benchmark = load('hst_diagnostic_common', HERE / 'benchmark.py')
guard = load('hst_diagnostic_guard', HERE / 'guard-depth.py')
benchmark.sanitize_environment()
ready = json.loads((REPO / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst/READY.json').read_text())
payload_before = benchmark.payload(ready)
build = json.loads((HERE / 'build-attempt3.json').read_text())
dataset = json.loads((Path(build['dataset']) / 'dataset.json').read_text())
case = next(case for case in dataset['cases'] if case['size'] == 100)
source = Path(case['clones']['candidate-v2'])
own = Path(tempfile.mkdtemp(prefix='nexus-hst-performance-profile-'))
home = own / 'home'
shutil.copytree(source, home)


def functions(profile):
    rows = []
    for (file, line, function), (primitive, calls, own_seconds, cumulative, _) in pstats.Stats(profile).stats.items():
        rows.append(dict(file=file, line=line, function=function, primitive_calls=primitive, calls=calls,
                         own_ms=own_seconds * 1000, cumulative_ms=cumulative * 1000))
    return sorted(rows, key=lambda row: row['cumulative_ms'], reverse=True)[:100]


class Cursor:
    def __init__(self, cursor, metric):
        self.raw, self.metric = cursor, metric

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def fetch(self, method, *args):
        started = time.perf_counter()
        try:
            return method(*args)
        finally:
            self.metric['fetch_ms'] += (time.perf_counter() - started) * 1000

    def fetchone(self):
        return self.fetch(self.raw.fetchone)

    def fetchall(self):
        return self.fetch(self.raw.fetchall)

    def fetchmany(self, *args):
        return self.fetch(self.raw.fetchmany, *args)

    def __iter__(self):
        return self

    def __next__(self):
        return self.fetch(next, self.raw)


class Connection:
    def __init__(self, raw, metrics):
        self.raw, self.metrics = raw, metrics

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def execute(self, sql, parameters=()):
        template_hash = benchmark.hashlib.sha256(sql.encode()).hexdigest()
        metric = self.metrics.setdefault(template_hash, dict(template_sha256=template_hash, calls=0,
            execute_ms=0.0, fetch_ms=0.0, template=None, plan=None, explain_error=None))
        started = time.perf_counter()
        cursor = self.raw.execute(sql, parameters)
        metric['execute_ms'] += (time.perf_counter() - started) * 1000
        metric['calls'] += 1
        if metric['template'] is None and sql.lstrip().upper().startswith(('SELECT', 'WITH')):
            # Original template only, never expanded SQL or bound parameters.
            metric['template'] = sql
            try:
                plan = self.raw.execute('EXPLAIN QUERY PLAN ' + sql, parameters)
                metric['plan'] = [dict(id=row[0], parent=row[1], detail=row[3]) for row in plan.fetchmany(4097)]
                if len(metric['plan']) > 4096:
                    metric['plan'] = metric['plan'][:4096]
                    metric['explain_error'] = 'PLAN_TRUNCATED'
                plan.close()
            except Exception as error:
                metric['explain_error'] = type(error).__name__
        return Cursor(cursor, metric)


@contextmanager
def sql_diagnostics(factory):
    original = factory.unit_of_work
    metrics = {}

    @contextmanager
    def wrapped(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            raw = uow.connection
            uow.connection = Connection(raw, metrics)
            try:
                yield uow
            finally:
                uow.connection = raw
    factory.unit_of_work = wrapped
    try:
        yield metrics
    finally:
        factory.unit_of_work = original


with guard.guarded():
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app
    from fastapi.testclient import TestClient
    from starlette.responses import JSONResponse
    fixtures = load('hst_diagnostic_clock', REPO / 'NEXUS_UI_R1/execution/fixtures.py')
    deps = bootstrap({}, ['--home', str(home), '--embedding-mode', 'off'])
    deps.clock = fixtures.ControlledClock(dataset['clock'])
    deps.config.feature_attention = deps.config.feature_observations = deps.config.feature_hitl = True
    app = build_app(deps)
    client = TestClient(app, client=('127.0.0.1', 65123))
    before = benchmark.productive(deps.connection_factory)
    service = app.state.home_entries
    original_read, original_render = service.read, JSONResponse.render
    service_profile, render_profile, transport_profile = cProfile.Profile(), cProfile.Profile(), cProfile.Profile()
    times = dict(service_ms=0.0, render_ms=0.0)

    def read(*args, **kwargs):
        started = time.perf_counter()
        try:
            return service_profile.runcall(original_read, *args, **kwargs)
        finally:
            times['service_ms'] += (time.perf_counter() - started) * 1000

    def render(self, content):
        started = time.perf_counter()
        try:
            return render_profile.runcall(original_render, self, content)
        finally:
            times['render_ms'] += (time.perf_counter() - started) * 1000

    params = dict(workspace_id='hst-perf', presentation_version=2, limit=10, preview=3)
    service.read, JSONResponse.render = read, render
    try:
        started = time.perf_counter()
        response = client.get('/api/v1/home/harness-board', params=params)
        elapsed = (time.perf_counter() - started) * 1000
        first = response.json().get('data', {})
    finally:
        service.read, JSONResponse.render = original_read, original_render
    result = dict(own_temp=str(own), layer='Diagnostic only, not p95 sample', payload_bytes=len(response.content),
        cprofile=dict(http_status=response.status_code, status=first.get('status'), http_elapsed_ms=elapsed,
            **times, transport_routing_auth_outside_service_and_other_ms=max(0, elapsed - sum(times.values())),
            service_functions=functions(service_profile), serialization_functions=functions(render_profile),
            profile_scope='Service and rendering profiled sequentially; no nested active Profiler.'))
    with sql_diagnostics(deps.connection_factory) as metrics:
        started = time.perf_counter()
        response = client.get('/api/v1/home/harness-board', params=params)
        elapsed = (time.perf_counter() - started) * 1000
    result['sql_diagnostic'] = dict(http_status=response.status_code, status=response.json().get('data', {}).get('status'),
        http_elapsed_ms=elapsed, statements=sorted(metrics.values(), key=lambda row: row['execute_ms'] + row['fetch_ms'], reverse=True),
        execute_ms=sum(row['execute_ms'] for row in metrics.values()), fetch_ms=sum(row['fetch_ms'] for row in metrics.values()),
        bounds='Transaction BEGIN/COMMIT excluded; no parameters/expanded SQL exported. EXPLAIN overhead is diagnostic, outside execute/fetch timers.')
    started = time.perf_counter()
    response = transport_profile.runcall(client.get, '/api/v1/home/harness-board', params=params)
    result['main_transport_diagnostic'] = dict(http_elapsed_ms=(time.perf_counter() - started) * 1000,
        http_status=response.status_code, status=response.json().get('data', {}).get('status'),
        functions=functions(transport_profile), note='Separate third GET; no nested service/render profiler or SQL proxy.')
    result['productive_drift'] = [name for name, value in benchmark.productive(deps.connection_factory).items() if value != before[name]]
    client.close()
    deps.connection_factory.close()
benchmark.origin_guard()
assert payload_before == benchmark.payload(ready)
result.update(payload_drift=False, wheel_sha256=ready['wheel_sha256'], source_commit=ready['source_commit'],
    runner_sha256=benchmark.sha(__file__), schema_unchanged=benchmark.schema(source / case['db_relative']) == benchmark.schema(home / case['db_relative']))
output = HERE / 'candidate100-v2-diagnostics.json'
benchmark.save(output, result)
print(json.dumps(dict(path=str(output), cprofile_ms=result['cprofile']['http_elapsed_ms'],
    service_ms=result['cprofile']['service_ms'], render_ms=result['cprofile']['render_ms'],
    other_ms=result['cprofile']['transport_routing_auth_outside_service_and_other_ms'],
    sql_ms=result['sql_diagnostic']['execute_ms'] + result['sql_diagnostic']['fetch_ms'],
    productive_drift=result['productive_drift'])), flush=True)
