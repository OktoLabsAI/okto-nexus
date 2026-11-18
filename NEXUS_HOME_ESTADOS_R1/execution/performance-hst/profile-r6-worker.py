"""Three separate R6 persistent-ASGI diagnostic GETs; not p95."""
from contextlib import contextmanager
import asyncio
import cProfile
import importlib.util
import json
from pathlib import Path
import pstats
import shutil
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module
benchmark=load('hst_r6_profile_common',HERE/'benchmark.py')
guard=load('hst_r6_profile_guard',HERE/'guard-depth.py')
ready_path=REPO/'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r6/READY.json'
ready=json.loads(ready_path.read_text())
assert ready['ready'] and ready['prefix_frozen']
benchmark.sanitize_environment()
payload_before=benchmark.payload(ready)
dataset_path=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-performance-dataset-3dccbd580bd34431bb61ba507dfa9559/dataset.json')
dataset=json.loads(dataset_path.read_text())
dataset_sha=benchmark.sha(dataset_path)
assert json.loads((dataset_path.parent/'.hst-owned.json').read_text())==dict(root=str(dataset_path.parent),kind='hst-performance-synthetic-only')
for name,value in dataset['helper_source_pins'].items():
    assert benchmark.sha(REPO/name)==value
case=next(c for c in dataset['cases'] if c['size']==100)
source=dataset_path.parent/'seed-100/home'
assert benchmark.sha(source/case['db_relative'])==case['database_sha256']
assert benchmark.schema(source/case['db_relative'])==case['schema_sha256']
own=Path(tempfile.mkdtemp(prefix='nexus-hst-performance-profile-r6-'))
home=own/'home';shutil.copytree(source,home)
assert benchmark.sha(home/case['db_relative'])==case['database_sha256']
assert benchmark.schema(home/case['db_relative'])==case['schema_sha256']
print(json.dumps(dict(phase='PRISTINE_CLONE_READY',own_temp=str(own),seed_sha=case['database_sha256'])),flush=True)

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


async def diagnostic():
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app
    from httpx import ASGITransport,AsyncClient
    from starlette.responses import JSONResponse
    fixtures=load('hst_r6_profile_clock',REPO/'NEXUS_UI_R1/execution/fixtures.py')
    deps=bootstrap({},['--home',str(home),'--embedding-mode','off'])
    deps.clock=fixtures.ControlledClock(dataset['clock'])
    deps.config.feature_attention=deps.config.feature_observations=deps.config.feature_hitl=True
    assert benchmark.schema(home/case['db_relative'])==case['schema_sha256']
    app=build_app(deps)
    client=AsyncClient(transport=ASGITransport(app,client=('127.0.0.1',65123)),base_url='http://hst-own.invalid')
    before=benchmark.productive(deps.connection_factory)
    service=app.state.home_entries
    original_read,original_render=service.read,JSONResponse.render
    service_profile,render_profile,transport_profile=cProfile.Profile(),cProfile.Profile(),cProfile.Profile()
    times=dict(service_ms=0.0,render_ms=0.0)
    def read(*args,**kwargs):
        started=time.perf_counter()
        try:return service_profile.runcall(original_read,*args,**kwargs)
        finally:times['service_ms']+=(time.perf_counter()-started)*1000
    def render(self,content):
        started=time.perf_counter()
        try:return render_profile.runcall(original_render,self,content)
        finally:times['render_ms']+=(time.perf_counter()-started)*1000
    params=dict(workspace_id='hst-perf',presentation_version=2,limit=10,preview=3)
    path='/api/v1/home/harness-board'
    result=dict(own_temp=str(own),layer='Diagnostic only, three separate GETs; no p95/SLO sample',
        transport='Persistent httpx ASGITransport/one loop, no TCP/lifespan',dataset_sha256=dataset_sha,seed_db_sha256=case['database_sha256'])
    try:
        service.read,JSONResponse.render=read,render
        try:
            started=time.perf_counter();response=await client.get(path,params=params)
            elapsed=(time.perf_counter()-started)*1000;first=response.json().get('data',{})
        finally:service.read,JSONResponse.render=original_read,original_render
        result.update(payload_bytes=len(response.content),cprofile=dict(http_status=response.status_code,status=first.get('status'),
            http_elapsed_ms=elapsed,**times,transport_routing_auth_outside_service_and_other_ms=max(0,elapsed-sum(times.values())),
            service_functions=functions(service_profile),serialization_functions=functions(render_profile),
            profile_scope='Sequential service and JSON render on their app thread; no enclosing profiler. Cumulative costs overlap.'))
        benchmark.save(own/'phase1-service.json',result['cprofile'])
        print(json.dumps(dict(phase='SERVICE_COMPLETE',http_ms=elapsed,service_ms=times['service_ms'],render_ms=times['render_ms'],
            top20=functions(service_profile)[:20])),flush=True)
        with sql_diagnostics(deps.connection_factory) as metrics:
            started=time.perf_counter();response=await client.get(path,params=params)
            elapsed=(time.perf_counter()-started)*1000
        result['sql_diagnostic']=dict(http_status=response.status_code,status=response.json().get('data',{}).get('status'),
            http_elapsed_ms=elapsed,statements=sorted(metrics.values(),key=lambda r:r['execute_ms']+r['fetch_ms'],reverse=True),
            execute_ms=sum(r['execute_ms'] for r in metrics.values()),fetch_ms=sum(r['fetch_ms'] for r in metrics.values()),
            bounds='Original SQL templates only; no bound parameters/expanded SQL. EXPLAIN overhead excluded from execute/fetch timers; transaction boundary costs excluded.')
        benchmark.save(own/'phase2-sql.json',result['sql_diagnostic'])
        print(json.dumps(dict(phase='SQL_COMPLETE',http_ms=elapsed,execute_ms=result['sql_diagnostic']['execute_ms'],fetch_ms=result['sql_diagnostic']['fetch_ms'])),flush=True)
        started=time.perf_counter();transport_profile.enable()
        try:response=await client.get(path,params=params)
        finally:transport_profile.disable()
        result['main_transport_diagnostic']=dict(http_elapsed_ms=(time.perf_counter()-started)*1000,http_status=response.status_code,
            status=response.json().get('data',{}).get('status'),functions=functions(transport_profile),
            note='Third GET only: main event-loop thread profiler. Worker service is not simultaneously profiled; cumulative async costs overlap.')
        result['productive_drift']=[k for k,v in benchmark.productive(deps.connection_factory).items() if v!=before[k]]
        result['schema_unchanged']=benchmark.schema(home/case['db_relative'])==case['schema_sha256']
        result['source_seed_unchanged']=benchmark.sha(source/case['db_relative'])==case['database_sha256']
        result['source_dataset_unchanged']=benchmark.sha(dataset_path)==dataset_sha
        return result
    finally:
        service.read,JSONResponse.render=original_read,original_render
        await client.aclose();deps.connection_factory.close()

with guard.guarded():
    result=asyncio.run(diagnostic())
benchmark.origin_guard()
payload_after=benchmark.payload(ready)
assert payload_before==payload_after
result.update(payload_drift=False,payload_files=sum(p['count'] for p in payload_after.values()),
    package_modules={k:dict(origin=v['origin'],count=v['count']) for k,v in payload_after.items()},
    wheel_sha256=ready['wheel_sha256'],source_commit=ready['source_commit'],runner_sha256=benchmark.sha(__file__))
output=HERE/'candidate-r6-100-v2-diagnostics.json'
benchmark.save(output,result)
print(json.dumps(dict(phase='DIAGNOSTIC_COMPLETE',path=str(output),schema_unchanged=result['schema_unchanged'],productive_drift=result['productive_drift'])),flush=True)
