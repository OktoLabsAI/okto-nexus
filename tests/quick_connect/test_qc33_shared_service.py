"""One real foreground HTTP owner, two canonical CLI connections, no daemon fake."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import pytest
import uvicorn
import test_local_realization
import test_terminal_connect as helpers
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.http.lock import ServeLock
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
from okto_nexus.adapters.outbound.service_manager.installation import INSTALLATION_NAME

local_setup=helpers.local_setup
checking=helpers.checking
terminal=helpers.terminal


@pytest.fixture(autouse=True)
def real_foreground_owner(monkeypatch):
    owned=[]
    def app_for(home):
        deps=bootstrap({},['--home',str(home),'--feature-harness-integrations','true',
            '--runtime-handoff-auto-claim-enabled','false'])
        lock=ServeLock(deps.config.home_dir,db_path=deps.config.db_path)
        lock.acquire()  # Production-generated generation and actual os.getpid.
        try:
            app=build_app(deps,lock=lock,release_lock=False)
        except BaseException:
            lock.release()
            raise
        owned.append(lock)
        return deps,app
    monkeypatch.setattr(test_local_realization,'app_for',app_for)
    yield owned
    records=[]
    for lock in owned:
        identity=dict(pid=os.getpid(),generation=lock.generation)
        lock.release()
        records.append(dict(**identity,guard_released=not lock.owned,metadata_absent=not lock.path.exists()))
    if os.environ.get('QC_DERIVATIVE_OUTPUT'):
        (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/'owner-cleanup.json').write_text(json.dumps(records,indent=2)+'\n')


def first_connection_rows(t,agent):
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        conn=uow.connection
        endpoints=[dict(r) for r in conn.execute('SELECT * FROM agent_endpoints WHERE agent_id=?',(agent,))]
        endpoint_ids=[r['endpoint_id'] for r in endpoints]
        assert len(endpoint_ids)==1
        endpoint=endpoint_ids[0]
        row=dict(conn.execute('SELECT * FROM agents WHERE agent_id=?',(agent,)).fetchone())
        row.pop('last_seen_at',None)  # Presence is not authorization renewal.
        return dict(agent=row,endpoints=endpoints,
            bindings=[dict(r) for r in conn.execute('SELECT * FROM execution_bindings WHERE endpoint_id=?',(endpoint,))],
            grants=[dict(r) for r in conn.execute('SELECT * FROM runtime_execution_grants WHERE endpoint_id=?',(endpoint,))],
            policies=[dict(r) for r in conn.execute('SELECT * FROM agent_execution_policies WHERE agent_id=?',(agent,))],
            overrides=[dict(r) for r in conn.execute('SELECT * FROM agent_runtime_overrides WHERE agent_id=?',(agent,))])


def test_g14_two_confirmations_reuse_one_genuine_ready_http_owner_without_changing_first(terminal,local_setup,
        real_foreground_owner,monkeypatch,capsys):
    t=terminal
    home=t.deps.config.home_dir.resolve()
    database=t.deps.config.db_path.resolve()
    lock,=real_foreground_owner
    assert lock.owned and lock._payload()['pid']==os.getpid()
    assert lock._payload()['generation']==lock.generation
    client=local_setup[2]
    sock=socket.socket()
    sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(t.app,host='127.0.0.1',port=port,
        lifespan='off',log_level='error',access_log=False))
    async def serve():
        await server.serve(sockets=[sock])
    running=client.portal.start_task_soon(serve)
    statuses=[]
    expected_instance=server_instance_id(home,database)
    def status():
        observed=inspect_local_server(home=home,database=database,host='127.0.0.1',port=port,timeout=2)
        assert observed['state']=='ready' and observed['ready_for_queries'] is True,observed
        assert observed['pid']==os.getpid()
        assert observed['generation']==lock.generation and observed['instance_id']==expected_instance
        statuses.append({key:observed[key] for key in ('pid','instance_id','generation','state','ready_for_queries')})
        return observed
    try:
        deadline=time.monotonic()+10
        while not server.started:
            assert not running.done() and time.monotonic()<deadline
            time.sleep(.02)
        ready=status()
        # There is no LocalOperatorHTTP or resolver override. The real resolver
        # correlates these held guards with the real HTTP readiness endpoint.
        assert connect.LocalOperatorHTTP is LocalOperatorHTTP
        assert connect.resolve_local_service.__module__=='okto_nexus.adapters.inbound.cli.service'
        spawned=[]
        def forbidden_spawn(*args,**kwargs):
            spawned.append(True)
            pytest.fail('Ready shared Server must not spawn a process per connection/ID',pytrace=False)
        monkeypatch.setattr(subprocess,'Popen',forbidden_spawn)
        monkeypatch.setattr('builtins.input',lambda *args:pytest.fail('JSON CLI must not read input'))
        monkeypatch.chdir(t.selection['project'])
        base=['connect','codex','App','--home',str(home),'--port',str(port),'--json','--no-chat']
        def invoke(profile,identifier,*extra):
            argv=[*base,'--profile',profile,'--id',identifier,*extra]
            code=main(argv)
            text=capsys.readouterr().out
            value=json.loads(text)
            assert code==0,value
            status()
            return value
        first=invoke('one','codex-a','--plan')
        first_result=invoke('one','codex-a','--approve',first['review_revision'])
        assert first_result['quick_connect']['status']=='connected'
        first_profile=home/'terminal/profiles/one.json'
        first_bytes=first_profile.read_bytes()
        first_saved=json.loads(first_bytes)
        ref_a=first_saved['result']['public_connection']['canonical_ref']
        first_before=first_connection_rows(t,ref_a['agent_id'])
        second=invoke('two','codex-b','--new-connection','--plan')
        assert second['selection']['workspace_id']==ref_a['workspace_id']
        assert first_profile.read_bytes()==first_bytes and first_connection_rows(t,ref_a['agent_id'])==first_before
        second_result=invoke('two','codex-b','--new-connection','--approve',second['review_revision'])
        assert second_result['quick_connect']['status']=='connected'
        second_saved=json.loads((home/'terminal/profiles/two.json').read_text())
        ref_b=second_saved['result']['public_connection']['canonical_ref']
        assert ref_a['server_id']==ref_b['server_id'] and ref_a['executor_id']==ref_b['executor_id']
        assert ref_a['workspace_id']==ref_b['workspace_id']
        for key in ('agent_id','binding_id','endpoint_id','workspace_binding_id'):
            assert ref_a[key]!=ref_b[key],key
        assert first_profile.read_bytes()==first_bytes and first_connection_rows(t,ref_a['agent_id'])==first_before
        assert len(t.turns)==2 and len(set(t.turns))==2 and spawned==[]
        counts={}
        with t.deps.connection_factory.unit_of_work(write=False) as uow:
            for table in ('workspaces','connection_public_ids','execution_bindings','runtime_execution_grants','connection_setup_commits',
                          'execution_operations','execution_sessions'):
                counts[table]=uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
        assert counts==dict(workspaces=1,connection_public_ids=2,execution_bindings=2,runtime_execution_grants=2,
            connection_setup_commits=2,execution_operations=0,execution_sessions=0)
        assert all((item['pid'],item['instance_id'],item['generation'])==
            (ready['pid'],ready['instance_id'],ready['generation']) for item in statuses)
        assert not (home/'service-context.json').exists() and not (home/'service-launch.json').exists()
        assert not (home/INSTALLATION_NAME).exists()
        proof=dict(pid=os.getpid(),instance_id=expected_instance,generation=lock.generation,
            server_kind='genuine foreground app/portal, not detached daemon',http_port=port,
            readiness='Unmodified inspect_local_server + real held ServeLock + real HTTP /api/v1/service',
            local_operator_http='real loopback socket, no transport stub',resolver='unmodified production resolver',
            statuses=statuses,canonical_refs=[ref_a,ref_b],counts=counts,synthetic_tests=2,
            version_probes=len(t.probes),process_launch_attempts=0,first_connection_rows_unchanged=True,
            first_profile_bytes_unchanged=True,user_service_installed=False)
        if os.environ.get('QC_DERIVATIVE_OUTPUT'):
            (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/'shared-service-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    finally:
        server.should_exit=True
        running.result(timeout=10)
        sock.close()
        if os.environ.get('QC_DERIVATIVE_OUTPUT'):
            (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/'http-cleanup.json').write_text(json.dumps(
                dict(uvicorn_task_done=running.done(),listener_closed=sock.fileno()==-1),indent=2)+'\n')
