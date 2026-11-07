import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest
from nexus_connector_core import RuntimeEvent
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.application.terminal_work import TerminalWork
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_vertical_inventory import _NativeFactory
from controller import Controller, Refused
from response_loss import CampaignState, FiniteResponseLoss


@pytest.fixture(autouse=True)
def forbidden_effects(monkeypatch):
    import subprocess, win32cred
    class NoProcess(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            raise AssertionError('native/subprocess forbidden')
    def deny(*args, **kwargs):
        raise AssertionError('vault forbidden')
    monkeypatch.setattr(subprocess,'Popen',NoProcess)
    for name in ('CredRead','CredWrite','CredDelete','CredEnumerate'):
        monkeypatch.setattr(win32cred,name,deny)


def event(scope, operation, method, total=10, *, thread='thread', turn='turn'):
    payload = {'thread_id':thread,'threadId':thread,'turn_id':turn}
    category, op = 'tool_activity', None
    if method=='thread/tokenUsage/updated':
        counts = dict(totalTokens=total,inputTokens=total,cachedInputTokens=0,outputTokens=0,reasoningOutputTokens=0)
        payload.update(turnId=turn,tokenUsage={'total':counts,'last':counts,'modelContextWindow':None})
    else:
        category,op = 'turn_state',operation
        payload.update(turn={'id':turn,'status':'completed' if method=='turn/completed' else 'inProgress'},
                       delivery_phase='terminal' if method=='turn/completed' else 'started')
        if method=='turn/completed':
            payload.update(delivery_outcome='success',output_text='NEXUS_CONNECTION_OK')
    return RuntimeEvent(scope['server_id'],scope['executor_id'],scope['session_id'],scope['stream_epoch'],
                        0,category,method,payload,op)


def wait_until(check, seconds=20):
    until=time.monotonic()+seconds
    while not check():
        assert time.monotonic()<until
        time.sleep(.03)


@pytest.fixture
def prepared(connected_local,tmp_path):
    setup,binding,native = connected_local
    deps,app,client,*_ = setup
    clock=[1000.0]
    controller=Controller(tmp_path/'controller.json',tmp_path,create=True,clock=lambda:clock[0])
    owner_stops=[]
    def owner_stop():
        owner_stops.append('owned-owner-stop')
        client.portal.call(app.state.connection_tests.shutdown)
        client.portal.call(app.state.embedded_dispatch_owner.close)
    controller.attach_owner('local',deps.config.home_dir,owner_stop)
    checkpoint=tmp_path/'work.json'
    def save(doc):
        checkpoint.write_text(json.dumps(doc),encoding='utf-8')
    def load():
        return json.loads(checkpoint.read_text())
    calls=[]
    def http(method,path,body=None):
        if method=='POST' and path.endswith('/runtime/operations'):
            stored=json.loads(controller.path.read_text())
            assert stored['requests'], 'No durable global reservation before dispatch'
            if body.get('client_intent_id')=='work-1':
                assert stored['collector']['state']['current_request']=='work-1'
        calls.append((method,path))
        response=client.request(method,path,json=body,headers={'X-Nexus-UI':'1'})
        if response.status_code>=400:
            raise ConnectionError('REQUEST_REFUSED','Synthetic canonical HTTP refusal')
        return response.json()
    connection=dict(state='done',server_id=binding['server_id'],selection=dict(agent='subject',client='codex',
        project=str(setup[6].resolve()),workspace_id=None,candidate_ref=None,provider_home=None),result={'binding':binding})
    faults=CampaignState(tmp_path/'faults.json',campaign_id='synthetic-controller')
    flow=TerminalWork(FiniteResponseLoss(http,load,faults,'local'),save,connection)
    controller.attach('local',flow)
    return SimpleNamespace(setup=setup,binding=binding,native=native,deps=deps,app=app,client=client,
        clock=clock,controller=controller,checkpoint=checkpoint,save=save,load=load,http=http,
        connection=connection,faults=faults,flow=flow,calls=calls,root=tmp_path,owner_stop=owner_stop,owner_stops=owner_stops)


def standalone_setup(t,monkeypatch,request='setup-1'):
    from okto_nexus.application import connection_test
    factory=_NativeFactory()
    monkeypatch.setattr(connection_test,'CopiedAdapterFactory',lambda environment:factory)
    entry={'status':'running','stage':'Preparing test','details':[]}
    configuration=dict(adapter_id='codex_app_server',provider_home=None,secret_bindings={},
                       workspace_root=str(t.setup[6]),harness_settings={})
    body={'agent_id':'subject','client_intent_id':request,'configuration':configuration}
    async def dispatch_task():
        stored=json.loads(t.controller.path.read_text())
        assert stored['requests'][request]['kind']=='setup' and not stored['requests'][request]['settled']
        entry['task']=asyncio.create_task(t.app.state.connection_tests.run(entry,body,t.setup[5]))
        t.app.state.connection_tests.tests[('operator',request)]=entry
    stop_calls=[]
    def stop():
        stop_calls.append('exact-owned-service-lifecycle-hook')
        t.client.portal.call(t.app.state.connection_tests.shutdown)
    t.controller.setup(request,'local',t.deps.config.home_dir,
                       lambda:t.client.portal.call(dispatch_task),stop)
    wait_until(lambda:bool(factory.native.sent) or entry['task'].done())
    assert factory.native.sent, entry
    return factory,entry,stop_calls


def setup_emit(t,factory,method,total=10):
    scope=dict(server_id='connection-test',executor_id='local',session_id='session',stream_epoch='epoch')
    t.client.portal.call(factory.native.queue.put,event(scope,'turn',method,total,thread='setup-thread'))


def work_started(t):
    operation=t.flow.resume()
    op=operation['submission_turn_operation_id'] or operation['operation_id']
    wait_receipt(t.setup,{'operation_id':op})
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        stream=dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    t.client.portal.call(t.native.native.queue.put,event(stream,op,'turn/started'))
    return op,stream


def test_setup_then_work_loss_recovery_real_pages_shared_accounting(prepared,monkeypatch):
    t=prepared
    factory,entry,stops=standalone_setup(t,monkeypatch)
    for method in ('turn/started','thread/tokenUsage/updated','turn/completed'):
        setup_emit(t,factory,method,17)
    wait_until(lambda:entry['task'].done())
    assert entry['status']=='succeeded' and factory.native.stopped
    assert t.controller.poll()['can_admit'] and t.controller.summary()['known_observed_tokens']==17
    second,second_entry,second_stops=standalone_setup(t,monkeypatch,'setup-2')
    for method in ('turn/started','thread/tokenUsage/updated','turn/completed'):
        setup_emit(t,second,method,19)
    wait_until(lambda:second_entry['task'].done())
    assert t.controller.poll()['can_admit'] and t.controller.summary()['known_observed_tokens']==36
    assert second_entry['status']=='succeeded'
    t.faults.arm('admission','local','work-1')
    with pytest.raises(ConnectionError):
        t.controller.work('work-1','local','Synthetic request')
    persisted=json.loads(t.controller.path.read_text())
    assert len(persisted['requests'])==3 and persisted['collector']['state']['current_request']=='work-1'
    # Reconstruct both observers. Neither path issues a second productive POST.
    t.faults=CampaignState(t.faults.path)
    t.flow=TerminalWork(FiniteResponseLoss(t.http,t.load,t.faults,'local'),t.save,t.connection,t.load())
    t.controller.close()
    t.controller=Controller(t.controller.path,t.root,clock=lambda:t.clock[0])
    t.controller.attach_owner('local',t.deps.config.home_dir,t.owner_stop)
    t.controller.attach('local',t.flow)
    op,stream=work_started(t)
    for method in ('thread/tokenUsage/updated','turn/completed'):
        t.client.portal.call(t.native.native.queue.put,event(stream,op,method,23))
    wait_receipt(t.setup,{'operation_id':op},stages=('SUCCEEDED',))
    wait_until(lambda:t.controller.poll()['can_admit'])
    assert t.controller.summary()['known_observed_tokens']==59
    assert t.controller.summary()['reserved_requests']==3
    assert sum(m=='POST' and p.endswith('/runtime/operations') for m,p in t.calls)==1
    assert t.native.opens==1 and len(t.native.native.sent)==1 and stops==second_stops==[]
    # Late usage on the already settled setup remains observed.
    before=t.controller.summary()
    assert not before['final_or_billed_usage']
    for index in range(1,4):
        result=t.controller.work('continue-'+str(index),'local','Synthetic continuation',stage='continuation')
        turn_op=result['operation_id']
        wait_receipt(t.setup,{'operation_id':turn_op})
        for method in ('turn/started','thread/tokenUsage/updated','turn/completed'):
            t.client.portal.call(t.native.native.queue.put,event(stream,turn_op,method,23+index,turn='turn-'+str(index)))
        wait_receipt(t.setup,{'operation_id':turn_op},stages=('SUCCEEDED',))
        wait_until(lambda:t.controller.poll() and t.controller.data['requests']['continue-'+str(index)]['settled'])
    assert t.controller.summary()['reserved_requests']==6  # two setup + four work/continuation
    calls_before=len(t.calls)
    with pytest.raises(Refused): t.controller.work('seventh','local','Forbidden')
    assert not any(m=='POST' for m,p in t.calls[calls_before:])
    closed=t.flow.submit(action='close',client_intent_id='close-owned')
    wait_receipt(t.setup,closed,stages=('SUCCEEDED',))


@pytest.mark.parametrize('cause',['budget','deadline','missing_usage','deadline_after_reload','boolean_usage'])
def test_actual_setup_journal_can_select_only_owned_service_shutdown(prepared,monkeypatch,cause):
    t=prepared
    factory,entry,stops=standalone_setup(t,monkeypatch)
    if cause=='deadline_after_reload':
        original_stop=t.controller.stops['local']
        t.controller.close()
        t.controller=Controller(t.controller.path,t.root,clock=lambda:t.clock[0])
        t.controller.attach('local',t.flow)
        with pytest.raises(Refused,match='OWNER_STOP_NOT_ATTACHED'):
            t.controller.work('not-dispatched','local','Must not dispatch')
        with pytest.raises(Refused,match='SETUP_OWNER_CHANGED'):
            t.controller.attach_setup_stop('setup-1',t.root,original_stop)
        t.controller.attach_setup_stop('setup-1',t.deps.config.home_dir,original_stop)
    setup_emit(t,factory,'turn/started')
    if cause=='budget': setup_emit(t,factory,'thread/tokenUsage/updated',100000)
    elif cause=='boolean_usage': setup_emit(t,factory,'thread/tokenUsage/updated',True)
    elif cause=='missing_usage': setup_emit(t,factory,'turn/completed')
    else: t.clock[0]+=120
    wait_until(lambda:t.controller.poll() and bool(stops))
    if cause=='missing_usage':
        # A completed setup without usage is UNKNOWN even if cleanup completed.
        assert not t.controller.summary()['can_admit']
    else:
        assert stops==['exact-owned-service-lifecycle-hook'] and entry['task'].done() and factory.native.stopped
    with pytest.raises(Refused): t.controller.work('work-after-stop','local','Must not dispatch')
    assert t.native.opens==0


@pytest.mark.parametrize('cause',['budget','deadline','missing_usage','gap'])
def test_work_monitor_selects_only_owned_canonical_interrupt(prepared,cause,request):
    t=prepared
    t.controller.work('work-1','local','Synthetic request')
    op,stream=work_started(t)
    if cause=='budget':
        t.client.portal.call(t.native.native.queue.put,event(stream,op,'thread/tokenUsage/updated',100000))
    elif cause=='missing_usage':
        t.client.portal.call(t.native.native.queue.put,event(stream,op,'turn/completed'))
    elif cause=='deadline': t.clock[0]+=120
    else:
        wait_until(lambda:t.controller.poll() and bool(t.controller.accounting['streams']))
        key=tuple(stream[k] for k in ('server_id','executor_id','session_id','stream_epoch'))
        def remove_owned_fault():
            with t.deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('UPDATE execution_event_watermarks SET gap_state=? '
                    'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND gap_state=?',
                    ('none',*key,'pending'))
        request.addfinalizer(remove_owned_fault)
        with t.deps.connection_factory.unit_of_work() as uow:
            changed=uow.connection.execute('UPDATE execution_event_watermarks SET gap_state=? '
                'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND gap_state=?',
                ('pending',*key,'none'))
            assert changed.rowcount==1
    wait_until(lambda:t.controller.poll() and t.controller.data['requests']['work-1']['stop_selected'] is not None)
    with pytest.raises(Refused): t.controller.work('second','local','Forbidden new work')
    # Canonical interrupt might be already inapplicable after terminal: never
    # substitute a new session, direct process kill or productive retry.
    assert t.controller.data['requests']['work-1']['stop_selected']['action']==('close' if cause=='missing_usage' else 'interrupt')
    assert t.native.opens==1
    assert sum(v=='send_turn' for v,_ in t.native.native.sent)==1
    controls=[v for v,_ in t.native.native.sent if v!='send_turn']
    assert set(controls)<= {'interrupt'}


def test_ambiguous_new_setup_journals_stop_owner_before_any_other_work(tmp_path):
    home=tmp_path/'own-home';home.mkdir()
    controller=Controller(tmp_path/'controller.json',tmp_path,create=True,clock=lambda:1000)
    stops=[]
    def dispatch():
        root=home/'connection-tests';root.mkdir()
        (root/('a'*32)).mkdir();(root/('b'*32)).mkdir()
    controller.setup('setup','local',home,dispatch,lambda:stops.append('owned-stop'))
    assert not controller.poll()['can_admit'] and stops==['owned-stop']
    assert controller.summary()['reserved_requests']==1


def test_two_controller_instances_cannot_lose_reservations(tmp_path):
    first=Controller(tmp_path/'controller.json',tmp_path,create=True,clock=lambda:1000)
    with pytest.raises(Refused,match='ALREADY_OWNED'):
        Controller(first.path,tmp_path,clock=lambda:1000)
    first.close()
    restored=Controller(first.path,tmp_path,clock=lambda:1000)
    assert restored.summary()['reserved_requests']==0
    restored.close()


def test_unknown_work_without_canonical_operation_stops_exact_owner(prepared):
    t=prepared
    original=t.flow.call.call
    def loss_before_post(method,path,body=None):
        if method=='POST' and path.endswith('/runtime/operations'):
            raise ConnectionError('OUTCOME_UNKNOWN','Synthetic transport uncertainty',possible_effect=True)
        return original(method,path,body)
    t.flow.call.call=loss_before_post
    with pytest.raises(ConnectionError): t.controller.work('work-1','local','Synthetic unknown')
    t.controller.poll()
    assert t.owner_stops==['owned-owner-stop'] and t.native.opens==0
    assert t.controller.data['requests']['work-1']['stop_selected']['action']=='stop_owner'
    assert not t.controller.summary()['can_admit']


def test_setup_close_submitted_without_owned_slot_release_is_not_settled(prepared,monkeypatch):
    import sqlite3
    t=prepared
    factory,entry,stops=standalone_setup(t,monkeypatch)
    for method in ('turn/started','thread/tokenUsage/updated','turn/completed'):
        setup_emit(t,factory,method,17)
    wait_until(lambda:entry['task'].done())
    assert entry['status']=='succeeded' and factory.native.stopped
    journals=list((t.deps.config.home_dir/'connection-tests').glob('*/journal.db'))
    assert len(journals)==1 and journals[0].resolve().is_relative_to(t.root.resolve())
    db=sqlite3.connect(journals[0])
    predicate="server_id='connection-test' AND executor_id='local' AND session_id='session' AND operation_id='open'"
    try:
        assert db.execute('SELECT released FROM owned_slot_reservations WHERE '+predicate).fetchall()==[(1,)]
        assert db.execute("SELECT stage FROM operations_v2 WHERE operation_id='close'").fetchall()==[('SUBMITTED',)]
        changed=db.execute('UPDATE owned_slot_reservations SET released=0 WHERE '+predicate+' AND released=1')
        assert changed.rowcount==1
        db.commit()
        summary=t.controller.poll()
        record=t.controller.data['requests']['setup-1']['monitor']
        assert record['close_stage']=='SUBMITTED' and record['owned_slot_released'] is False
        assert summary['known_observed_tokens']==17 and not summary['can_admit']
        assert not t.controller.data['requests']['setup-1']['settled'] and stops==[]
    finally:
        db.execute('UPDATE owned_slot_reservations SET released=1 WHERE '+predicate+' AND released=0')
        db.commit();db.close()
    assert t.controller.poll()['can_admit']
