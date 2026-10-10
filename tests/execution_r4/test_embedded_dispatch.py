"""Public local operations are dispatched by serve, without WSS or Connector."""
import asyncio
import json
from pathlib import Path
import time
import threading
from contextlib import contextmanager

import pytest
from nexus_connector_core import CoreError

from okto_nexus.bootstrap import embedded_dispatch
from okto_nexus.adapters.inbound.http import runtime_v1
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.outbound.sqlite.execution_receipts import append_execution_receipt
from test_local_realization import local_setup, publish
from test_binding_operator import prepare_operator
from test_vertical_inventory import _NativeFactory
from test_embedded_inventory import app_for
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def qualified_contract(monkeypatch):
    # Exercise real installed negotiation; native peers remain synthetic.
    info = runtime_v1.protocol_info()
    assert info["remote_execution_ready"] is True
    assert embedded_dispatch.protocol_info() == info


@pytest.fixture
def connected_local(local_setup):
    return connect_local(local_setup)


def connect_local(local_setup, *, secret_bindings=None, agent_id="subject"):
    deps,app,client,headers,body,candidate,root=local_setup
    owner=app.state.embedded_dispatch_owner
    assert owner.pump is not None
    class NativeFactory(_NativeFactory):
        opens=0
        async def open(self,*args,**kwargs):
            self.opens+=1
            self.native=_NativeFactory().native
            return await super().open(*args,**kwargs)
    native=NativeFactory()
    owner.native_factory=native
    response=publish(local_setup,changes={"secret_bindings":secret_bindings or {}})
    assert response.status_code==201,response.text
    view=response.json()
    _,apply=prepare_operator(client,headers,dict(client_intent_id="automatic-binding-" + agent_id,agent_id_hint=agent_id,
        executor_id=view["executor_id"],adapter_id=body["adapter_id"],candidate_ref=body["candidate_ref"],
        inventory_revision=body["inventory_revision"],realization_ref=view["realization_ref"],
        workspace_id=view["workspace_id"],alias="automatic-local"))
    apply["client_intent_id"] = "apply-" + agent_id
    response=client.post("/v1/connections/bindings:apply",json=apply,headers=headers["operator"])
    assert response.status_code==200,response.text
    binding=response.json()
    grant=client.post("/api/v1/harness/grants",headers=headers["operator"],json={
        "actor_agent_id":agent_id,"endpoint_id":binding["endpoint_id"],
        "actions":["open","send","steer","interrupt","close"],"max_executions":10,
        "expires_at":iso_plus(deps.clock.now_iso(),600)})
    assert grant.status_code==200,grant.text
    return local_setup,binding,native


def admit(setup,binding,intent_id,intent,**options):
    _,_,client,headers,*_=setup
    response=client.post("/v1/runtime/intents:resolve",headers=headers["subject"],json={
        "client_intent_id":intent_id,"intent":intent,"binding_id":binding["binding_id"],
        "workspace_binding_id":binding["workspace_binding_id"],**options})
    assert response.status_code==200,response.text
    resolution=response.json()
    assert resolution["can_submit"],resolution
    request={k:resolution[k] for k in ("client_intent_id","operation_id","resolution_revision","intent_hash")}
    response=client.post("/v1/runtime/operations",headers=headers["subject"],json=request)
    assert response.status_code==202,response.text
    replay=client.post("/v1/runtime/operations",headers=headers["subject"],json=request)
    assert replay.status_code==200 and replay.json()["operation_id"]==resolution["operation_id"]
    return resolution


def wait_receipt(setup,resolution,stages=("SUBMITTED","SUCCEEDED")):
    _,app,client,headers,*_=setup
    # A test watchdog includes durable I/O on loaded Windows runners; native
    # deadlines are covered separately. Keep failures fully diagnosable.
    until=time.monotonic()+30
    while True:
        view=client.get(f"/v1/runtime/operations/{resolution['operation_id']}",headers=headers["subject"]).json()
        if view.get("executor_stage") in stages:
            return view
        owner=app.state.embedded_dispatch_owner
        assert owner.failure is None,repr(owner.failure)
        assert owner.pump.error is None,repr(owner.pump.error)
        assert time.monotonic()<until,json.dumps(view, sort_keys=True)
        time.sleep(.02)


def test_serve_dispatches_local_open_turn_controls_and_close(connected_local):
    setup,binding,native=connected_local
    deps,app,client,headers,*_=setup
    opened=admit(setup,binding,"auto-open","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    assert native.opens==1
    session=opened["scope"]["session_id"]
    sent=admit(setup,binding,"auto-send","turn.submit",session_id=session,text="Hello")
    wait_receipt(setup,sent)
    steered=admit(setup,binding,"auto-steer","turn.steer",session_id=session,text="Continue carefully.",
                  target={"kind":"native_turn_id","expected_turn_id":"turn-from-native"})
    wait_receipt(setup,steered)
    interrupted=admit(setup,binding,"auto-interrupt","turn.interrupt",session_id=session,
                      target={"kind":"current_run","expected_turn_id":None})
    wait_receipt(setup,interrupted)
    closed=admit(setup,binding,"auto-close","runtime.close",session_id=session)
    wait_receipt(setup,closed,stages=("SUCCEEDED",))
    assert native.native.stopped and native.opens==1
    assert [verb for verb,_ in native.native.sent]==["send_turn","steer","interrupt"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_link_tickets").fetchone()[0]==0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_local_publications").fetchone()[0]==5
        assert uow.connection.execute("SELECT lifecycle_state FROM execution_sessions").fetchone()[0]=="CLOSED"
        assert uow.connection.execute("SELECT MIN(attempt_no),MAX(attempt_no) FROM execution_dispatch_outbox").fetchone()[:]==(1,1)
        revision=uow.connection.execute("SELECT MAX(receipt_revision) FROM execution_receipts WHERE operation_id=?",
                                        (closed["operation_id"],)).fetchone()[0]
    # Recover the crash window after accepting the terminal receipt but before
    # acknowledging its publication obligation, without creating a new fact.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_local_publications SET terminal=0 WHERE operation_id=?",(closed["operation_id"],))
    until=time.monotonic()+5
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            terminal=uow.connection.execute("SELECT terminal FROM execution_local_publications WHERE operation_id=?",
                                            (closed["operation_id"],)).fetchone()[0]
            assert uow.connection.execute("SELECT MAX(receipt_revision) FROM execution_receipts WHERE operation_id=?",
                                          (closed["operation_id"],)).fetchone()[0]==revision
        if terminal:
            break
        assert time.monotonic()<until
        time.sleep(.02)
    binary=Path(setup[5].executable)
    assert binary.resolve().parent==setup[6].resolve().parent
    binary.unlink()
    history=client.get(f"/v1/runtime/operations/{closed['operation_id']}",headers=headers["subject"])
    assert history.status_code==200 and history.json()["executor_stage"]=="SUCCEEDED"


@pytest.mark.parametrize('failure', ['expired', 'revoked'])
def test_denied_renewal_releases_only_its_session_and_keeps_executor_ready(connected_local, monkeypatch, failure):
    from okto_nexus.errors import ErrorCode
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    opened = admit(setup, binding, 'expiring-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    session_id = opened['scope']['session_id']
    owner = app.state.embedded_dispatch_owner
    other = admit(setup, binding, 'unrelated-open', 'runtime.start', new_session=True)
    wait_receipt(setup, other)
    async def deny(**kwargs):
        if failure == 'expired':
            raise OktoNexusError(ErrorCode.CONFLICT, 'The authority has expired.', {})
        raise CoreError('AGENT_REVOKED', 'lease_renew')
    current = owner.sessions[session_id]
    monkeypatch.setattr(current['executor'], 'renew_r4', deny)
    client.portal.call(owner._renew_owned, session_id, current)
    assert owner.failure is None and not owner._stopping.is_set()
    assert session_id not in owner.sessions
    assert other['scope']['session_id'] in owner.sessions
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?',
            (session_id,)).fetchone()[:] == ('CLOSED', 'CLOSED')
        assert uow.connection.execute('SELECT control_state FROM execution_executors').fetchone()[0] == 'CONTROL_READY'
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
            (other['scope']['session_id'],)).fetchone()[0] == 'READY'
    wait_receipt(setup, admit(setup, binding, 'unrelated-close', 'runtime.close',
        session_id=other['scope']['session_id']), stages=('SUCCEEDED',))
    again = admit(setup, binding, 'after-expiry-open', 'runtime.start', new_session=True)
    wait_receipt(setup, again)
    wait_receipt(setup, admit(setup, binding, 'after-expiry-close', 'runtime.close',
        session_id=again['scope']['session_id']), stages=('SUCCEEDED',))


def test_stale_local_owner_cannot_start_native_work(connected_local):
    setup,binding,native=connected_local
    deps,app,*_=setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET generation=generation+1 WHERE kind='embedded'")
    until=time.monotonic()+5
    owner=app.state.embedded_dispatch_owner
    while owner.pump.error is None and owner.failure is None:
        assert time.monotonic()<until
        time.sleep(.02)
    assert native.opens==0


def test_local_owner_renews_installed_lease(connected_local):
    setup,binding,native=connected_local
    deps,app,*_=setup
    app.state.embedded_dispatch_owner.leases.max_duration_ms=2000
    opened=admit(setup,binding,"renew-open","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    until=time.monotonic()+6
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            serial=uow.connection.execute("SELECT MAX(lease_serial) FROM execution_leases WHERE status='ACTIVE'").fetchone()[0]
        if serial is not None and serial>=2:
            break
        assert app.state.embedded_dispatch_owner.failure is None,repr(app.state.embedded_dispatch_owner.failure)
        assert time.monotonic()<until
        time.sleep(.02)
    closed=admit(setup,binding,"renew-close","runtime.close",session_id=opened["scope"]["session_id"])
    wait_receipt(setup,closed,stages=("SUCCEEDED",))
    assert native.opens==1


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'codex_app_server', 'claude_stream'], indirect=True)
def test_opening_renews_before_native_ready(connected_local):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    entered, release = threading.Event(), threading.Event()
    original = native.open

    async def held(*args, **kwargs):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        return await original(*args, **kwargs)

    native.open = held
    owner.leases.max_duration_ms = 4000
    opened = admit(setup, binding, 'held-renew-open', 'runtime.start', new_session=True)
    try:
        assert entered.wait(10)
        sid = opened['scope']['session_id']
        session = owner.sessions[sid]
        assert session['opening'] and session['gate'].locked()
        client.portal.start_task_soon(owner._renew_owned, sid, session).result(timeout=3)
        assert not release.is_set() and native.opens == 0
        with deps.connection_factory.unit_of_work(write=False) as uow:
            serial = uow.connection.execute('SELECT MAX(lease_serial) FROM execution_leases WHERE session_id=?',
                                            (sid,)).fetchone()[0]
        assert serial >= 2
    finally:
        release.set()
    wait_receipt(setup, opened)
    assert native.opens == 1 and owner.failure is None


def test_receipt_replay_requires_current_embedded_owner(connected_local):
    setup,binding,native=connected_local
    deps,app,*_=setup
    opened=admit(setup,binding,"receipt-owner","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        frame=json.loads(uow.connection.execute("SELECT canonical_frame FROM execution_receipts LIMIT 1").fetchone()[0])
    owner=app.state.embedded_inventory_owner
    assert append_execution_receipt(deps.connection_factory,embedded_owner=owner,frame=frame).reused
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET generation=generation+1 WHERE kind='embedded'")
    with pytest.raises(OktoNexusError):
        append_execution_receipt(deps.connection_factory,embedded_owner=owner,frame=frame)
    assert native.opens==1


def test_blocked_session_does_not_delay_other_session_renewal(connected_local):
    setup,binding,native=connected_local
    deps,app,client,*_=setup
    owner=app.state.embedded_dispatch_owner
    owner.leases.max_duration_ms=4000
    first=admit(setup,binding,"independent-first","runtime.start",new_session=True)
    wait_receipt(setup,first)
    second=admit(setup,binding,"independent-second","runtime.start",new_session=True)
    wait_receipt(setup,second)
    gate=owner.sessions[first["scope"]["session_id"]]["gate"]
    client.portal.call(gate.acquire)
    try:
        until=time.monotonic()+5
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                serial=uow.connection.execute("SELECT MAX(lease_serial) FROM execution_leases WHERE session_id=? AND status='ACTIVE'",
                                              (second["scope"]["session_id"],)).fetchone()[0]
            if serial is not None and serial>=2:
                break
            assert owner.failure is None,repr(owner.failure)
            assert time.monotonic()<until
            time.sleep(.02)
        assert gate.locked() and native.opens==2
    finally:
        client.portal.call(gate.release)


def test_lost_receipt_persistence_never_reopens_operation(connected_local, request):
    setup,binding,native=connected_local
    deps,app,client,headers,*_=setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_local_receipt BEFORE INSERT ON execution_receipts "
                               "BEGIN SELECT RAISE(ABORT,'technical receipt failure'); END")
    def restore_storage():
        # The test observes persistent failure while the owner is live. Its
        # teardown must restore storage so final publication can drain.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('DROP TRIGGER IF EXISTS reject_local_receipt')
    request.addfinalizer(restore_storage)
    opened=admit(setup,binding,"lost-receipt","runtime.start",new_session=True)
    until=time.monotonic()+10
    while 'subject' not in app.state.embedded_dispatch_owner.agents.errors:
        assert time.monotonic()<until
        time.sleep(.02)
    assert native.opens==1

    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_local_publications").fetchone()[0]==1
    replay=client.post("/v1/runtime/operations",headers=headers["subject"],json={
        k:opened[k] for k in ("client_intent_id","operation_id","resolution_revision","intent_hash")})
    assert replay.status_code==200 and replay.json()["operation_id"]==opened["operation_id"]
    assert native.opens==1
    until=time.monotonic()+5
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == "CONTROL_READY"
            state=uow.connection.execute("SELECT state FROM execution_agent_recovery WHERE agent_id='subject'").fetchone()[0]
        if state=="RECOVERING":
            break
        assert time.monotonic()<until
        time.sleep(.02)
    blocked=client.post("/v1/runtime/intents:resolve",headers=headers["subject"],json={
        "client_intent_id":"after-failure","intent":"runtime.start","binding_id":binding["binding_id"],
        "workspace_binding_id":binding["workspace_binding_id"],"new_session":True})
    assert blocked.status_code==200,blocked.text
    assert not blocked.json()["can_submit"] and "agent_recovering" in blocked.json()["blockers"]


def test_control_lane_remains_available_while_turn_send_waits(connected_local):
    setup,binding,native=connected_local
    _,app,client,*_=setup
    opened=admit(setup,binding,"held-open","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    entered=threading.Event()
    release=asyncio.Event()
    original=native.native.send
    async def held(verb,*args,**kwargs):
        if verb=="send_turn":
            entered.set()
            await release.wait()
        return await original(verb,*args,**kwargs)
    native.native.send=held
    try:
        admit(setup,binding,"held-send","turn.submit",session_id=opened["scope"]["session_id"],text="Wait")
        assert entered.wait(3)
        interrupted=admit(setup,binding,"held-interrupt","turn.interrupt",session_id=opened["scope"]["session_id"],
                          target={"kind":"current_run","expected_turn_id":None})
        wait_receipt(setup,interrupted)
        assert ("interrupt",interrupted["operation_id"]) in native.native.sent
        assert not release.is_set()
    finally:
        client.portal.call(release.set)


def test_cancelled_shutdown_observer_keeps_native_producer_owned(connected_local):
    setup,binding,native=connected_local
    _,app,client,*_=setup
    opened=admit(setup,binding,"shutdown-open","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    entered=threading.Event()
    release=asyncio.Event()
    original=native.native.send
    async def held(verb,*args,**kwargs):
        entered.set()
        await release.wait()
        return await original(verb,*args,**kwargs)
    native.native.send=held
    try:
        admit(setup,binding,"shutdown-turn","turn.submit",session_id=opened["scope"]["session_id"],text="Wait")
        assert entered.wait(3)
        async def scenario():
            owner=app.state.embedded_dispatch_owner
            observer=asyncio.create_task(owner.close())
            await asyncio.sleep(.05)
            observer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await observer
            assert owner.workers and not owner._close_task.done()
            release.set()
            await asyncio.wait_for(owner.close(),5)
            assert not owner.workers and owner.pump.task.done()
        client.portal.call(scenario)
    finally:
        client.portal.call(release.set)


def test_dispatch_cleanup_failure_still_drains_core(connected_local,monkeypatch):
    setup,binding,native=connected_local
    _,app,client,*_=setup
    opened=admit(setup,binding,"cleanup-error","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    owner=app.state.embedded_dispatch_owner
    original=owner.pump.stop
    async def failed_stop():
        await original()
        raise OSError("Technical outbox cleanup failure")
    with monkeypatch.context() as patch:
        patch.setattr(owner.pump,"stop",failed_stop)
        with pytest.raises(OSError,match="Technical outbox cleanup failure"):
            client.portal.call(owner._close)
    assert native.native.stopped and not owner.workers and not owner.renewals


@pytest.mark.parametrize("filename",["session-retained.db","owned-slots.db"])
def test_retained_journal_requires_recovery_before_local_readiness(tmp_path,filename):
    home=tmp_path/"home"
    journal=home/"core-runtime"/filename
    journal.parent.mkdir(parents=True)
    journal.write_bytes(b"Existing retained journal must not be treated as an empty runtime")
    deps,app=app_for(home)
    with TestClient(app):
        assert app.state.embedded_dispatch_owner.pump is None
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0]=="RECOVERING"
    assert journal.read_bytes()==b"Existing retained journal must not be treated as an empty runtime"


@pytest.mark.parametrize("missing_journal", [False, True])
def test_restart_recovers_historical_receipt_without_provider(tmp_path,monkeypatch,missing_journal):
    with contextmanager(local_setup.__wrapped__)(tmp_path,monkeypatch,None) as setup:
        setup,binding,native=connected_local.__wrapped__(setup)
        deps,app,client,headers,_,candidate,_=setup
        opened=admit(setup,binding,"recover-open","runtime.start",new_session=True)
        wait_receipt(setup,opened)
        source=app.state.embedded_dispatch_owner.channel
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("CREATE TRIGGER reject_cold_receipt BEFORE INSERT ON execution_receipts "
                "BEGIN SELECT RAISE(ABORT,'technical receipt failure'); END")
        closed=admit(setup,binding,"recover-close","runtime.close",session_id=opened["scope"]["session_id"])
        until=time.monotonic()+10
        while 'subject' not in app.state.embedded_dispatch_owner.agents.errors:
            assert time.monotonic()<until
            time.sleep(.02)
        assert native.native.stopped
        # This case models a process exit before publishing the retained
        # receipt. Normal graceful shutdown now retries publication, so it
        # cannot be used to simulate that crash boundary with a permanent
        # database fault. Leave the real journal intact for the next owner.
        async def exit_before_publication():
            assert native.native.stopped
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute(
                    "SELECT 1 FROM execution_receipts WHERE operation_id=?",
                    (closed["operation_id"],)).fetchone() is None
        monkeypatch.setattr(app.state.embedded_dispatch_owner,
                            "_publish_shutdown_history", exit_before_publication)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("DROP TRIGGER reject_cold_receipt")
    Path(candidate.executable).unlink()
    from types import SimpleNamespace
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory,"discover_local_candidates",lambda **_:SimpleNamespace(candidates=()))
    if missing_journal:
        for file in (tmp_path/"home/core-runtime").glob("session-*.db"):
            file.rename(tmp_path / (file.name + ".retained"))
    deps,app=app_for(tmp_path/"home")
    with TestClient(app) as client:
        owner=app.state.embedded_dispatch_owner
        assert owner.channel.connection_generation>source.connection_generation
        assert owner.pump is not None
        assert ('subject' in owner.agents.blocked) == missing_journal
        assert not owner.host._runtime_tasks
        assert native.opens==1
        history=client.get(f"/v1/runtime/operations/{closed['operation_id']}",headers=headers["subject"])
        assert history.status_code==200,history.text
        if missing_journal:
            try:
                assert isinstance(owner.agents.errors['subject'],FileNotFoundError)
                assert history.json().get("executor_stage")!="SUCCEEDED"
                assert not list((tmp_path/"home/core-runtime").glob("session-*.db"))
            finally:
                # Restore the deliberately removed durable evidence before
                # asking graceful shutdown to publish it. While it is absent,
                # shutdown correctly retains the unresolved recovery state.
                for retained in tmp_path.glob('session-*.db.retained'):
                    retained.rename(tmp_path/'home/core-runtime'/retained.name.removesuffix('.retained'))
            recovered = client.portal.call(owner.retry_recovery, 'subject')
            assert recovered['state'] == 'READY', recovered
            assert native.opens == 1
            wait_receipt((deps, app, client, headers), closed, stages=('SUCCEEDED',))
        else:
            assert owner.recovery_failure is None,repr(owner.recovery_failure)
            assert history.json()["executor_stage"]=="SUCCEEDED"
            with deps.connection_factory.unit_of_work(write=False) as uow:
                row=uow.connection.execute("SELECT source_connection_id,source_connection_generation FROM execution_receipts "
                    "WHERE operation_id=?",(closed["operation_id"],)).fetchone()
                assert tuple(row)==(source.connection_id,source.connection_generation)
                assert uow.connection.execute("SELECT terminal FROM execution_local_publications WHERE operation_id=?",
                    (closed["operation_id"],)).fetchone()[0]==1
                assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0]=="CONTROL_READY"
                assert uow.connection.execute("SELECT lifecycle_state FROM execution_sessions").fetchone()[0]=="CLOSED"


def test_cancelled_history_observer_keeps_journal_owned(tmp_path,monkeypatch):
    from okto_nexus.bootstrap import runtime_host
    from nexus_connector_core import OperationKey
    async def scenario():
        host=runtime_host.EmbeddedRuntimeHost(tmp_path/"core")
        key=OperationKey("server","executor","operation")
        path=host._journal_path(key.executor_id,"session")
        path.parent.mkdir()
        path.write_bytes(b"Technical history journal placeholder")
        entered,release,closed=asyncio.Event(),asyncio.Event(),asyncio.Event()
        class Journal:
            async def get_receipt(self,key):
                entered.set()
                await release.wait()
                return None
            async def aclose(self):
                closed.set()
        async def open_history(path):
            return Journal()
        monkeypatch.setattr(runtime_host,"open_journal",open_history)
        observer=asyncio.create_task(host.historical_receipt(session_id="session",key=key))
        await entered.wait()
        observer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await observer
        assert host._history_tasks and not closed.is_set()
        drain=asyncio.create_task(host.shutdown())
        await asyncio.sleep(.01)
        assert not drain.done()
        release.set()
        await asyncio.wait_for(drain,2)
        assert closed.is_set() and not host._history_tasks
        assert not host._runtime_tasks and host._ledger_task is None
    asyncio.run(scenario())


def test_local_events_commit_and_reapply_lost_core_ack(connected_local,monkeypatch):
    from nexus_connector_core import RuntimeEvent
    setup,binding,native=connected_local
    deps,app,client,*_=setup
    opened=admit(setup,binding,"event-open","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    owner=app.state.embedded_dispatch_owner
    with deps.connection_factory.unit_of_work(write=False) as uow:
        scope=dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
    async def scenario():
        _,journal=await owner.host._runtime_tasks[(scope["executor_id"],scope["session_id"])]
        original=journal.acknowledge_events
        failed=asyncio.Event()
        async def ack(cursor,through):
            if through>0 and not failed.is_set():
                failed.set()
                raise OSError("Technical Core ACK failure")
            return await original(cursor,through)
        monkeypatch.setattr(journal,"acknowledge_events",ack)
        await native.native.queue.put(RuntimeEvent(scope["server_id"],scope["executor_id"],
            scope["session_id"],scope["stream_epoch"],0,"text_delta","technical.output",{"text":"Hello"}))
        await asyncio.wait_for(failed.wait(),5)
    client.portal.call(scenario)
    until=time.monotonic()+5
    while 'subject' not in owner.agents.errors:
        assert time.monotonic()<until
        time.sleep(.02)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT committed_contiguous FROM execution_event_watermarks").fetchone()[0]==1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_event_ingress").fetchone()[0]==1
    # A successor host applies the committed ACK even though the first owner
    # failed before acknowledging Core. It does not duplicate the event.
    client.portal.call(owner.close)
    async def recover():
        from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost
        host=EmbeddedRuntimeHost(owner.host.store_dir)
        # Verify ACK application through the actual publisher using the current
        # owner identity, with a reopened history-only host.
        original_host=owner.host
        owner.host=host
        try:
            assert not await owner.events.step(scope)
            async def compact(journal):
                count,_=await journal.compact_acked(max_rows=128)
                assert count==1
            await host.with_history(executor_id=scope["executor_id"],session_id=scope["session_id"],read=compact)
        finally:
            owner.host=original_host
            await host.shutdown()
    client.portal.call(recover)


def test_local_event_owner_change_prevents_commit(connected_local):
    from dataclasses import asdict
    from nexus_connector_core import RuntimeEvent, R4_PREVIEW_REVISION
    from okto_nexus.application.execution_events import commit_execution_events
    setup,binding,_=connected_local
    deps,app,*_=setup
    opened=admit(setup,binding,"event-fence","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    owner=app.state.embedded_dispatch_owner
    with deps.connection_factory.unit_of_work() as uow:
        scope=dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
        uow.connection.execute("UPDATE execution_executors SET generation=generation+1 WHERE kind='embedded'")
    frame={k:scope[k] for k in ("server_id","executor_id","binding_id","agent_id","session_id","stream_epoch")}
    event=asdict(RuntimeEvent(scope["server_id"],scope["executor_id"],scope["session_id"],scope["stream_epoch"],1,
        "text_delta","technical.output",{"text":"Hello"}))
    event.pop("operation_id")
    frame.update(type="event.batch",protocol_major=1,contract_revision=R4_PREVIEW_REVISION,
        connection_id=owner.channel.connection_id,connection_generation=owner.channel.connection_generation,events=[event])
    with pytest.raises((ValueError,OktoNexusError)):
        commit_execution_events(deps.connection_factory,channel=owner.channel,frame=frame,embedded_owner=owner)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_event_ingress").fetchone()[0]==0


@pytest.mark.parametrize('agent_state', ['active', 'inactive', 'archived'])
def test_restart_publishes_uncommitted_native_events(tmp_path,monkeypatch,agent_state):
    from nexus_connector_core import RuntimeEvent
    from okto_nexus.bootstrap import embedded_events
    with contextmanager(local_setup.__wrapped__)(tmp_path,monkeypatch,None) as setup:
        setup,binding,native=connected_local.__wrapped__(setup)
        deps,app,client,headers,_,candidate,_=setup
        opened=admit(setup,binding,"replay-events","runtime.start",new_session=True)
        wait_receipt(setup,opened)
        owner=app.state.embedded_dispatch_owner
        with deps.connection_factory.unit_of_work(write=False) as uow:
            scope=dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
        failed_publications = []
        def unavailable(*args,**kwargs):
            failed_publications.append(True)
            raise OSError("Technical event storage failure")
        with monkeypatch.context() as patch:
            patch.setattr(embedded_events,"commit_execution_events",unavailable)
            client.portal.call(native.native.queue.put,RuntimeEvent(scope["server_id"],scope["executor_id"],
                scope["session_id"],scope["stream_epoch"],0,"text_delta","technical.output",{"text":"Retained"}))
            until=time.monotonic()+5
            while not failed_publications:
                assert time.monotonic()<until
                time.sleep(.02)
            # A transient Server write failure retains Core history for retry;
            # it must not contain an otherwise healthy native session.
            assert 'subject' not in owner.agents.errors
            # Freeze publication at the crash boundary. The normal shutdown
            # publisher must not make this a test of already committed events.
            client.portal.call(owner._stopping.set)
            async def exit_before_events():
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_event_ingress').fetchone()[0] == 0
            monkeypatch.setattr(owner, '_publish_shutdown_history', exit_before_events)
        if agent_state == 'archived':
            response = client.delete('/api/v1/agents/subject', headers=headers['operator'])
            assert response.status_code == 200, response.text
        elif agent_state == 'inactive':
            response = client.patch('/api/v1/agents/subject', headers=headers['operator'], json={'is_active': False})
            assert response.status_code == 200, response.text
    Path(candidate.executable).unlink()
    for _ in range(2):
        deps,app=app_for(tmp_path/"home")
        with TestClient(app) as client:
            owner=app.state.embedded_dispatch_owner
            assert owner.recovery_failure is None,repr(owner.recovery_failure)
            assert not owner.host._runtime_tasks and owner.pump is not None
            with deps.connection_factory.unit_of_work(write=False) as uow:
                rows=uow.connection.execute("SELECT payload_json FROM execution_event_ingress").fetchall()
                assert len(rows)==1 and json.loads(rows[0][0])["payload"]=={"text":"Retained"}
                assert uow.connection.execute("SELECT committed_contiguous,gap_state FROM execution_event_watermarks").fetchone()[:]==(1,"none")
                assert bool(uow.connection.execute("SELECT is_active FROM agents WHERE agent_id='subject'").fetchone()[0]) == (agent_state == 'active')
    assert native.opens==1


@pytest.mark.parametrize("fault",[None,"occupied_ledger","missing_ledger","untracked_journal","event_gap"])
def test_released_resources_reconcile_before_new_admission(tmp_path,monkeypatch,fault):
    with contextmanager(local_setup.__wrapped__)(tmp_path,monkeypatch,None) as setup:
        setup,binding,native=connected_local.__wrapped__(setup)
        deps,app,client,headers,*_=setup
        opened=admit(setup,binding,"resource-open","runtime.start",new_session=True)
        wait_receipt(setup,opened)
        old_channel=app.state.embedded_dispatch_owner.channel
        with deps.connection_factory.unit_of_work(write=False) as uow:
            stream=dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
    # The normal Core shutdown observed native stop and persisted release.
    assert native.native.stopped
    store=tmp_path/"home/core-runtime"
    if fault=="occupied_ledger":
        from nexus_connector_core import SQLiteOwnedSlotLedger,OperationKey
        async def retain():
            ledger=SQLiteOwnedSlotLedger(store/"owned-slots.db")
            try:
                await ledger.reserve_owned_slot(OperationKey(old_channel.server_id,old_channel.executor_id,"unknown-opening"),"unknown-session")
            finally:
                await ledger.aclose()
        asyncio.run(retain())
    elif fault=="missing_ledger":
        (store/"owned-slots.db").rename(store/"retained-ledger.db")
    elif fault=="untracked_journal":
        (store/"session-untracked.db").write_bytes(b"Unaccounted journal")
    elif fault=="event_gap":
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO execution_event_watermarks "
                "(server_id,executor_id,session_id,stream_epoch,committed_contiguous,gap_state) VALUES (?,?,?,?,0,'pending')",
                tuple(stream[k] for k in ("server_id","executor_id","session_id","stream_epoch")))
    deps,app=app_for(tmp_path/"home")
    with TestClient(app) as client:
        owner=app.state.embedded_dispatch_owner
        assert owner.channel.connection_generation>old_channel.connection_generation
        assert not owner.host._runtime_tasks
        with deps.connection_factory.unit_of_work(write=False) as uow:
            state=uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0]
            session=uow.connection.execute("SELECT lifecycle_state FROM execution_sessions WHERE session_id=?",
                (opened["scope"]["session_id"],)).fetchone()[0]
        if fault == "event_gap":
            assert state == "CONTROL_READY" and owner.pump is not None
            assert "subject" in owner.agents.blocked
            assert native.opens == 1
        elif fault:
            assert state=="RECOVERING" and owner.pump is None
            assert owner.recovery_failure is not None
            assert native.opens==1
        else:
            assert state=="CONTROL_READY" and session=="CLOSED"
            assert owner.recovery_failure is None and owner.pump is not None
            owner.native_factory=native
            next_setup=(deps,app,client,headers,*setup[4:])
            next_open=admit(next_setup,binding,"after-recovery","runtime.start",new_session=True)
            wait_receipt(next_setup,next_open)
            assert native.opens==2
