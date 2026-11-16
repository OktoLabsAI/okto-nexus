"""One finite actual-TCP overview benchmark over four disposable datasets.

No production handler is patched. Auth and clock are unchanged; discovery and
ASGI lifespan are disabled only in these owned fixture servers. Every request
uses the real loopback operator path and real Home route. Only a read-only
fixture middleware and SQLite observation/write barrier surround that path.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import multiprocessing
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from time import perf_counter
from types import SimpleNamespace

import httpx
import uvicorn


ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).resolve().parent
FROZEN_HEAD = '3d95aad8c1b5d2e6354cd872512586fd7a02aec9'
SAMPLES = 20
CASES = [(1,10,100),(10,10,100),(100,10,100),(100,1000,100000)]
SOURCE_PATHS = ['scripts/measure_home_evolution.py','pyproject.toml','uv.lock',
    'src/okto_nexus/domain/home.py','src/okto_nexus/application/home.py',
    'src/okto_nexus/application/home_ports.py','src/okto_nexus/adapters/inbound/http/home.py',
    'src/okto_nexus/adapters/outbound/sqlite/home.py','src/okto_nexus/adapters/outbound/sqlite/attention.py'] + [
    f'src/okto_nexus/adapters/outbound/sqlite/attention_{name}.py'
    for name in ('native','operations','approvals','results','authority','external')]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix+'.writing')
    temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def load_measurement():
    spec = importlib.util.spec_from_file_location('owned_home_http_measurement', ROOT/'scripts/measure_home_evolution.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObserveAllFactoryUses:
    """Observe the shared factory across auth and projection, not just Home."""
    def __init__(self, factory):
        self.original = factory.unit_of_work
        self.lock = threading.Lock()
        self.current = []
        self.active = self.peak = 0
        factory.unit_of_work = self.unit_of_work

    @contextmanager
    def unit_of_work(self, *, write=True):
        with self.original(write=write) as uow:
            conn = uow.connection
            before = conn.total_changes
            statements, denied = [], []
            mutations = {getattr(sqlite3,name) for name in (
                'SQLITE_INSERT','SQLITE_UPDATE','SQLITE_DELETE','SQLITE_CREATE_TABLE','SQLITE_DROP_TABLE',
                'SQLITE_ALTER_TABLE','SQLITE_CREATE_INDEX','SQLITE_DROP_INDEX','SQLITE_CREATE_TRIGGER',
                'SQLITE_DROP_TRIGGER','SQLITE_CREATE_VIEW','SQLITE_DROP_VIEW','SQLITE_CREATE_VTABLE','SQLITE_DROP_VTABLE')}

            def authorize(action, *args):
                if action in mutations:
                    denied.append(action)
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            with self.lock:
                self.active += 1
                self.peak = max(self.peak,self.active)
            conn.set_trace_callback(statements.append)
            conn.set_authorizer(authorize)
            try:
                yield uow
            finally:
                conn.set_trace_callback(None)
                conn.set_authorizer(None)
                with self.lock:
                    self.current.append(dict(declared_write=write,sql_statements=len(statements),
                        row_changes=conn.total_changes-before,denied_mutations=len(denied)))
                    self.active -= 1

    def take(self):
        with self.lock:
            assert self.active == 0
            result = dict(uows=self.current,peak_uows=self.peak)
            self.current,self.peak=[],0
            return result


async def serve(app, pipe, counts, observer, runtime):
    config = uvicorn.Config(app,host='127.0.0.1',port=0,lifespan='off',
        log_config=None,log_level='critical',access_log=False,timeout_graceful_shutdown=10)
    sock = config.bind_socket()
    port = sock.getsockname()[1]
    server = uvicorn.Server(config)

    async def controls():
        while not server.started and not server.should_exit:
            await asyncio.sleep(.01)
        pipe.send(dict(ready=True,port=port,dataset=counts,**runtime,
            http_protocol=config.http_protocol_class.__module__+'.'+config.http_protocol_class.__name__))
        while not server.should_exit:
            if pipe.poll():
                command = pipe.recv()
                if command == 'stats':
                    pipe.send(observer.take())
                elif command == 'stop':
                    server.should_exit = True
                    pipe.send({'stopping':True})
                    return
                else:
                    raise ValueError('UNKNOWN_OWN_CONTROL')
            await asyncio.sleep(.01)

    watcher = asyncio.create_task(controls())
    try:
        await server.serve(sockets=[sock])
    finally:
        watcher.cancel()
        sock.close()


def server_process(pipe, home, case):
    deps = None
    try:
        m = load_measurement()
        from fastapi.responses import JSONResponse
        from okto_nexus.bootstrap import embedded_inventory
        import okto_nexus
        embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
        deps = m.bootstrap({'OKTO_NEXUS_EMBEDDING_MODE':'off','OKTO_NEXUS_TELEMETRY_ENABLED':'0'},['--home',home])
        counts,_ = m.seed(deps,*case)
        app = m.build_app(deps)

        @app.middleware('http')
        async def own_read_only(request, call_next):
            if request.method not in {'GET','HEAD','OPTIONS'}:
                return JSONResponse({'fixture':'Owned read-only benchmark'},status_code=405)
            return await call_next(request)

        observer = ObserveAllFactoryUses(deps.connection_factory)
        runtime = dict(runtime_started=False,discovery_enabled=False,clock_patched=False,
            authentication_path='Unmodified canonical local-loopback operator; no API key or personal account used',
            nexus_origin=str(Path(okto_nexus.__file__).resolve()),python=sys.version,python_executable=sys.executable)
        asyncio.run(serve(app,pipe,counts,observer,runtime))
    except BaseException as error:
        try:
            pipe.send({'ready':False,'error_type':type(error).__name__,'message':str(error)})
        except (EOFError,OSError):
            pass
        raise
    finally:
        if deps is not None:
            deps.connection_factory.close()
        pipe.close()


def receive(pipe, process, timeout=120):
    if not pipe.poll(timeout):
        raise TimeoutError(f'OWN_CONTROL_TIMEOUT_PID_{process.pid}_ALIVE_{process.is_alive()}')
    return pipe.recv()


def summarize(values):
    ordered = sorted(values)
    return dict(p50_ms=ordered[len(ordered)//2] if len(ordered)%2 else
        (ordered[len(ordered)//2-1]+ordered[len(ordered)//2])/2,
        p95_ms=ordered[math.ceil(.95*len(ordered))-1])


def measure_case(home, case, children):
    ctx = multiprocessing.get_context('spawn')
    parent,child = ctx.Pipe()
    process = ctx.Process(target=server_process,args=(child,str(home),case))
    process.start()
    children.append(process)
    child.close()
    cleanup = {}
    try:
        ready = receive(parent,process)
        assert ready.get('ready'),ready
        samples,requests=[],[]
        url = f'http://127.0.0.1:{ready["port"]}'
        with httpx.Client(base_url=url,trust_env=False,timeout=30,
                limits=httpx.Limits(max_connections=1,max_keepalive_connections=1)) as client:
            for number in range(SAMPLES+1):
                started = perf_counter()
                response = client.get('/api/v1/home/overview',params={'workspace_id':'home-performance-synthetic'})
                elapsed = (perf_counter()-started)*1000
                assert response.status_code == 200,('HTTP_STATUS',response.status_code)
                assert response.headers.get('cache-control') == 'no-store'
                envelope = response.json()
                assert envelope['ok'] is True
                data = envelope['data']
                assert data['scope'] == {'workspace_id':'home-performance-synthetic'}
                assert data['work']['status'] == data['agents']['status'] == data['server_attention']['status'] == 'ready'
                assert data['work']['total']==case[1] and data['agents']['total']==case[0]
                assert len(data['work']['items'])==10 and data['server_attention']['total']==0
                assert data['event_cursor']==case[2]
                parent.send('stats')
                stats = receive(parent,process)
                assert all(row['row_changes']==row['denied_mutations']==0 for row in stats['uows']),stats
                record = dict(http_ms=elapsed,http_status=response.status_code,
                    decoded_body_bytes=len(response.content),downloaded_body_bytes=response.num_bytes_downloaded,
                    content_encoding=response.headers.get('content-encoding'),
                    generated_at=data['generated_at'],snapshot_id=data['snapshot_id'],
                    event_cursor=data['event_cursor'],server_id=data['server_id'],
                    total_uows=len(stats['uows']),sql_statements=sum(row['sql_statements'] for row in stats['uows']),**stats)
                if number==0:
                    warmup=record
                else:
                    samples.append(elapsed)
                    requests.append(record)
        return dict(dataset=ready['dataset'],server=ready,samples=20,discarded_warmups=1,
            warmup=warmup,http_round_trip=summarize(samples),sample_requests=requests,
            one_read_uow_per_request=all(row['total_uows']==1 and row['uows'][0]['declared_write'] is False for row in requests),
            sql_statements_per_request=sorted({row['sql_statements'] for row in requests}),
            database_changes=0,cleanup=cleanup)
    finally:
        if process.is_alive():
            try:
                parent.send('stop')
                cleanup['normal_stop_ack']=receive(parent,process,30).get('stopping') is True
            except (EOFError,OSError,TimeoutError):
                cleanup['normal_stop_ack']=False
        process.join(30)
        cleanup.update(pid=process.pid,forced=False,exit_code=process.exitcode,physically_exited=not process.is_alive())
        if process.is_alive():
            # Exact owned child handle only; never an unrelated service/process.
            cleanup['forced']=True
            process.terminate()
            process.join(15)
            cleanup.update(exit_code=process.exitcode,physically_exited=not process.is_alive())
        parent.close()
        assert cleanup['physically_exited'] and cleanup['exit_code']==0 and not cleanup['forced'],cleanup


def main():
    output = OUTPUT/'measurement.json'
    selected = OUTPUT/'run-selected.json'
    assert not output.exists() and not selected.exists(),'RUN_ALREADY_SELECTED_DO_NOT_RESTART'
    source_pins = {name:sha(ROOT/name) for name in SOURCE_PATHS}
    for name in SOURCE_PATHS:
        expected = subprocess.run(['rtk','proxy','git','rev-parse',FROZEN_HEAD+':'+name],cwd=ROOT,
            check=True,capture_output=True,text=True).stdout.strip()
        current = subprocess.run(['rtk','proxy','git','hash-object','--path='+name,name],cwd=ROOT,
            check=True,capture_output=True,text=True).stdout.strip()
        assert current==expected,('FROZEN_SOURCE_CHANGED',name)
    write(selected,dict(selected_at=datetime.now(timezone.utc).isoformat(),pid=__import__('os').getpid(),
        source_head=FROZEN_HEAD,input_sha256=source_pins,runner_sha256=sha(__file__),cases=CASES,samples=20))
    pythonw=Path(sys.executable).with_name('pythonw.exe')
    if sys.platform=='win32' and pythonw.is_file():
        multiprocessing.set_executable(str(pythonw))
    own = Path(tempfile.mkdtemp(prefix='nexus-home-pr12-http-')).resolve()
    assert own.parent==Path(tempfile.gettempdir()).resolve() and own.name.startswith('nexus-home-pr12-http-')
    result = dict(status='IN_PROGRESS',source_head=FROZEN_HEAD,input_sha256=source_pins,
        environment=dict(os=platform.platform(),python=platform.python_version(),sqlite=sqlite3.sqlite_version,
            cpu_logical=__import__('os').cpu_count(),ram_bytes=34073251840),cases=[],
        limitations=['Real local HTTP full-body round trip, excluding subsequent client JSON parsing and own control-pipe stats collection.',
            'One discarded real HTTP warmup plus20 warm keep-alive requests per dataset; no browser/SSE or app lifespan/startup during timing.',
            'Unmodified canonical loopback authorization and real clock. No personal auth, provider or native executable.',
            'Shared factory observation covers auth/projection UoWs; SQLite write barrier and total_changes check reject mutations.',
            'Owned read-only fixture middleware adds slight overhead and blocks every non-read request. No route/response/data is mocked.',
            'General Windows load is not otherwise controlled;500ms remains a local acceptance target, not a production SLO guarantee.'])
    children = []
    try:
        for index,case in enumerate(CASES):
            measured = measure_case(own/f'case-{index}',case,children)
            result['cases'].append(measured)
            write(output,result)
            print(json.dumps({key:measured[key] for key in ('dataset','http_round_trip','one_read_uow_per_request','sql_statements_per_request','cleanup')}),flush=True)
        assert all(sha(ROOT/name)==digest for name,digest in source_pins.items()),'INPUT_CHANGED_DURING_HTTP_RUN'
        result['status']='PASS_MEASURED_NOT_SLO_APPROVAL'
        result['latency_target_ms']=500
        result['latency_target_met']=[case['http_round_trip']['p95_ms']<=500 for case in result['cases']]
        result['all_source_pins_unchanged']=True
        result['finished_at']=datetime.now(timezone.utc).isoformat()
        write(output,result)
    except BaseException as error:
        result['status']='INCOMPLETE_OR_FAILED'
        result['error_type']=type(error).__name__
        result['error']=str(error)
        write(output,result)
        raise
    finally:
        # Only the verified, newly allocated root after all owned child joins.
        assert own.parent==Path(tempfile.gettempdir()).resolve() and own.name.startswith('nexus-home-pr12-http-')
        if all(not process.is_alive() for process in children):
            shutil.rmtree(own)
        else:
            result['own_data_preserved_for_live_child']=str(own)
            result['live_owned_child_pids']=[process.pid for process in children if process.is_alive()]
            write(output,result)


if __name__=='__main__':
    multiprocessing.freeze_support()
    main()
