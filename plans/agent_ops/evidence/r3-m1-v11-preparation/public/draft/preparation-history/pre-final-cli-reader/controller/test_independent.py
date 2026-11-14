"""Actual synthetic Core journals, fake canonical API, no real service/provider."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

import pytest
from nexus_connector_core import RuntimeEvent
from nexus_connector_core.journal import SQLiteJournal
from okto_nexus.application.terminal_connection import ConnectionError

from controller import Controller, POLICY, ANCESTRY, Refused
from independent_journal import CanonicalIntentReader, CoreJournalReader, JournalUnknown
from canonical_fixture import scope, event
import token_collector as tokens


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    import socket,subprocess,urllib.request
    def denied(*args,**kwargs):raise AssertionError('External effect forbidden')
    # Windows asyncio implements its private wake-up socketpair with loopback
    # sockets. Permit only that stdlib self-pipe construction; no application
    # socket connect/bind/listen, HTTP, service or provider call is allowed.
    internal=threading.local();original_pair=socket.socketpair
    def pair(*args,**kwargs):
        internal.pair=True
        try:return original_pair(*args,**kwargs)
        finally:internal.pair=False
    monkeypatch.setattr(socket,'socketpair',pair)
    for name in ('connect','connect_ex','bind','listen'):
        original=getattr(socket.socket,name)
        def guarded(sock,*args,_original=original,**kwargs):
            if not getattr(internal,'pair',False):return denied()
            return _original(sock,*args,**kwargs)
        monkeypatch.setattr(socket.socket,name,guarded)
    monkeypatch.setattr(subprocess,'Popen',denied)
    monkeypatch.setattr(urllib.request,'urlopen',denied)
    import win32cred
    for name in ('CredRead','CredWrite','CredDelete','CredEnumerate'):monkeypatch.setattr(win32cred,name,denied)


DDL='''
CREATE TABLE execution_client_intents(server_id TEXT,actor_agent_id TEXT,client_intent_id TEXT,operation_id TEXT,resolved_json TEXT,initial_turn_json TEXT);
CREATE TABLE execution_operations(server_id TEXT,executor_id TEXT,operation_id TEXT,subject_agent_id TEXT,binding_id TEXT,workspace_id TEXT,workspace_binding_id TEXT,session_id TEXT,admission_state TEXT,action TEXT);
CREATE TABLE execution_sessions(server_id TEXT,executor_id TEXT,session_id TEXT,binding_id TEXT,workspace_id TEXT,workspace_binding_id TEXT,owner_generation INTEGER,open_operation_id TEXT,lifecycle_state TEXT,lease_state TEXT,stream_epoch TEXT);
CREATE TABLE execution_receipts(server_id TEXT,executor_id TEXT,operation_id TEXT,stage TEXT,error_code TEXT,possible_effect INTEGER,retry_safe INTEGER,receipt_revision INTEGER);
'''


class CanonicalFixture:
    def __init__(self,home):
        self.path=home/'nexus.db'
        with sqlite3.connect(self.path) as db:db.executescript(DDL);db.execute('PRAGMA journal_mode=WAL')

    def admit(self,name,selected,*,continuation=False):
        opening='open-'+name if not continuation else 'turn-'+name
        operation='turn-'+name
        resolved=dict(client_intent_id=name,scope=selected)
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO execution_client_intents VALUES(?,?,?,?,?,?)',
                (selected['server_id'],'operator',name,opening,json.dumps(resolved),
                 json.dumps({'operation_id':operation}) if not continuation else None))
            db.execute('INSERT INTO execution_operations VALUES(?,?,?,?,?,?,?,?,?,?)',
                (selected['server_id'],selected['executor_id'],operation,selected['agent_id'],selected['binding_id'],
                 selected['workspace_id'],selected['workspace_binding_id'],selected['session_id'],'ACCEPTED','turn.submit'))
            if not continuation:
                db.execute('INSERT INTO execution_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (selected['server_id'],selected['executor_id'],selected['session_id'],selected['binding_id'],
                     selected['workspace_id'],selected['workspace_binding_id'],selected['session_owner_generation'],
                     opening,'READY','ACTIVE','epoch'))
        return {'scope':selected,'operation_id':opening,'submission_turn_operation_id':operation}

    def terminal(self,name,selected,stage='SUCCEEDED',*,preopen=False):
        operation=('open-' if preopen else 'turn-')+name
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO execution_receipts VALUES(?,?,?,?,?,?,?,?)',
                (selected['server_id'],selected['executor_id'],operation,stage,
                 'PREPARATION_FAILED' if preopen else None,0 if preopen else 1,1 if preopen else 0,1))
            if preopen:db.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED',stream_epoch=NULL WHERE session_id=?",(selected['session_id'],))


class JournalFixture:
    def __init__(self,path,selected):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.path=path;self.scope=selected;self.journal=SQLiteJournal(path);self.sequence=0

    def emit(self,method,name,total=10,*,thread='thread',turn=None,epoch='epoch'):
        self.sequence+=1
        value=event(self.sequence,method,total=total,op='turn-'+name,turn=turn or 'turn-'+name,
            thread=thread,selected=self.scope,epoch=epoch)
        value.pop('received_at')
        asyncio.run(self.journal.append_event(RuntimeEvent(**value)))

    def complete(self,name,total=10,*,thread='thread'):
        for method in ('turn/started','thread/tokenUsage/updated','turn/completed'):self.emit(method,name,total,thread=thread)

    def close(self):self.journal.close()


class Flow:
    def __init__(self,fixture,selected,control,*,release=None,entered=None):
        self.fixture=fixture;self.selected=selected;self.control=control
        self.document={};self.calls=[];self.release=release;self.entered=entered
        self.call=self.raw

    def raw(self,method,path,body=None):
        self.calls.append((method,path))
        if method=='GET':return self.selected
        saved=json.loads(self.control.path.read_text())
        name=body['client_intent_id']
        assert name in saved['requests'] and saved['requests'][name]['kind']=='work'
        assert name in saved['collector']['state']['requests']
        result=self.fixture.admit(name,self.selected,continuation=not body['new_session'])
        self.document['session_id']=self.selected['session_id']
        if self.entered:self.entered.set()
        if self.release:assert self.release.wait(30)
        return result

    def submit(self,text=None,*,client_intent_id,new_session=False,**kwargs):
        # Canonical scope/drift validation remains before each effect, not cached away.
        self.call('GET','/api/v1/runtime-management/connections/me')
        return self.call('POST','/api/v1/runtime-management/runtime/operations',
            {'client_intent_id':client_intent_id,'new_session':new_session})


def create_control(root,clock=None,*,create=True):
    approval={'status':'USER_APPROVED','proposal_revision':POLICY['revision'],'proposal_sha256':'a'*64,
        'policy':deepcopy(POLICY),'ancestry':deepcopy(ANCESTRY),'user_quote':'SYNTHETIC ONLY',
        'campaign_root':str(root.resolve())}
    ap=root/'synthetic-approval.json';ap.write_text(json.dumps(approval),encoding='utf-8')
    return Controller(root/'controller.json',root,create=create,clock=clock or time.time,
        monotonic=clock or time.monotonic,approval_path=ap,approval_sha256=hashlib.sha256(ap.read_bytes()).hexdigest(),
        expected_proposal_sha256='a'*64)


def attach(control,fixture,root,home,lane='local',selected=None,**kwargs):
    selected=selected or scope(lane)
    pre={k:selected[k] for k in tokens.PRE_SCOPE}
    owner=home if lane=='local' else root/'connector-state'
    owner.mkdir(exist_ok=True)
    stops=[]
    control.attach_owner(lane,owner,lambda:stops.append('normal-stop'))
    reader=CanonicalIntentReader(root,home,server_id=selected['server_id'],actor_id='operator',pre_scope=pre)
    journal=CoreJournalReader(root,owner,lane)
    control.attach_observer(lane,reader,journal)
    flow=Flow(fixture,selected,control,**kwargs)
    control.attach_api_flow(lane,flow)
    return flow,journal,stops


def consume(control,timeout=3):
    end=time.monotonic()+timeout
    while control.api.thread is not None and time.monotonic()<end:
        control.poll();time.sleep(.01)
    control.poll()
    assert control.api.thread is None
    return control.take_api_result()


def test_actual_core_journal_accounts_while_http_worker_is_blocked(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home)
    control=create_control(tmp_path);release=threading.Event();entered=threading.Event()
    flow,reader,stops=attach(control,fixture,tmp_path,home,release=release,entered=entered)
    writer=None
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={})
        assert entered.wait(1)
        writer=JournalFixture(reader.path(flow.selected),flow.selected)
        observed=(POLICY['preventive_cumulative_tokens']-POLICY['carry_in_tokens'])//2
        writer.complete('one',observed)
        fixture.terminal('one',flow.selected)
        summary=control.poll()
        assert summary['known_observed_tokens']==POLICY['carry_in_tokens']+observed
        assert control.api.thread.is_alive() and not stops
        assert control.data['requests']['one']['settled']
        assert len([v for v in flow.calls if v[0]=='POST'])==1
        assert control.data['independent_observation']['source']=='CORE_LOCAL_PROJECTION_NOT_SERVER_PUBLICATION'
    finally:
        release.set();consume(control);control.close()
        if writer:writer.close()


def test_threshold_and_late_post_fence_share_one_normal_stop(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home)
    control=create_control(tmp_path);release=threading.Event();entered=threading.Event()
    flow,reader,stops=attach(control,fixture,tmp_path,home,release=release,entered=entered)
    writer=None
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={})
        assert entered.wait(1)
        writer=JournalFixture(reader.path(flow.selected),flow.selected)
        writer.emit('turn/started','one');writer.emit('thread/tokenUsage/updated','one',(POLICY['preventive_cumulative_tokens']-POLICY['carry_in_tokens']))
        assert control.poll()['known_observed_tokens']==200000
        for _ in range(3):control.poll()
        assert stops==['normal-stop'] and control.fence.event.is_set()
        assert len(control.data['independent_owner_stops'])==1
        assert control.data['independent_owner_stops']['local']['native_exit_confirmed'] is False
        release.set();consume(control)
        control.schedule_read('late',lambda:flow.call('POST','/api/v1/runtime-management/runtime/operations',{}))
        result=consume(control)
        assert not result['ok'] and len([v for v in flow.calls if v[0]=='POST'])==1
    finally:
        release.set();consume(control);control.close()
        if writer:writer.close()


def test_deadline_tick_does_not_wait_for_blocked_http_and_cannot_replay(tmp_path):
    now=[1000.];home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home)
    control=create_control(tmp_path,lambda:now[0]);release=threading.Event();entered=threading.Event()
    flow,reader,stops=attach(control,fixture,tmp_path,home,release=release,entered=entered)
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});assert entered.wait(1)
        for _ in range(121):now[0]+=1.;control.poll()
        assert control.api.thread.is_alive() and stops==['normal-stop']
        assert 'DEADLINE120' in control.data['faults']
        with pytest.raises(Refused):control.start_work('two','local','no',binding=flow.selected,checkpoint={})
        assert control.summary()['new_reserved_requests']==1
    finally:release.set();consume(control);control.close()


def test_terminal_preopen_failure_preserves_reservation_no_usage_inference(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);control=create_control(tmp_path)
    flow,reader,stops=attach(control,fixture,tmp_path,home)
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});consume(control)
        fixture.terminal('one',flow.selected,'FAILED',preopen=True)
        result=control.poll();record=control.data['requests']['one']
        assert result['known_observed_tokens']==POLICY['carry_in_tokens'] and not result['can_admit']
        assert record['preopen_failure']['billed_tokens'] is None
        assert not record['preopen_failure']['useful_result_confirmed'] and not record['settled']
        assert result['new_reserved_requests']==1 and stops==['normal-stop']
        assert not reader.path(flow.selected).exists()
    finally:control.close()


@pytest.mark.parametrize('lane',['local','connector'])
def test_journal_privacy_scope_and_real_layout(tmp_path,lane):
    owner=tmp_path/'owner';owner.mkdir();selected=scope(lane)
    reader=CoreJournalReader(tmp_path,owner,lane);writer=JournalFixture(reader.path(selected),selected)
    try:
        secret=RuntimeEvent(selected['server_id'],selected['executor_id'],selected['session_id'],'epoch',1,
            'text_delta','output/secret',{'text':'PRIVATE TRANSCRIPT PASSWORD','token':'PRIVATE TOKEN'})
        asyncio.run(writer.journal.append_event(secret));writer.sequence=1
        writer.complete('one',12)
        page=reader.read(selected)
        assert page['count']==4 and page['events'][0]['payload']=={}
        assert 'PRIVATE' not in json.dumps(page)
        assert reader.path(selected).name==('executor-journal.db' if lane=='connector' else
            'session-'+hashlib.sha256((selected['executor_id']+'\0'+selected['session_id']).encode()).hexdigest()+'.db')
        wrong=dict(selected,session_id='wrong-session')
        assert reader.read(wrong) is None
    finally:writer.close()


@pytest.mark.parametrize('change',['gap','epoch','watermark','body_scope','counter_type'])
def test_corrupted_or_rolled_back_journal_fails_closed(tmp_path,change):
    owner=tmp_path/'owner';owner.mkdir();selected=scope();reader=CoreJournalReader(tmp_path,owner,'local')
    writer=JournalFixture(reader.path(selected),selected)
    try:
        writer.complete('one',10);reader.read(selected)
        with sqlite3.connect(writer.path) as db:
            if change=='gap':db.execute('DELETE FROM events WHERE sequence=2')
            elif change=='epoch':db.execute("UPDATE event_streams SET stream_epoch='changed'")
            elif change=='watermark':db.execute('UPDATE event_streams SET next_sequence=2')
            elif change=='body_scope':db.execute("UPDATE events SET body=json_set(body,'$.session_id','other') WHERE sequence=2")
            else:db.execute("UPDATE events SET body=json_set(body,'$.payload.tokenUsage.total.totalTokens','10') WHERE sequence=2")
        with pytest.raises(JournalUnknown):reader.read(selected)
    finally:writer.close()


def test_missing_journal_may_arrive_late_but_disappearance_is_not_fresh_start(tmp_path):
    owner=tmp_path/'owner';owner.mkdir();selected=scope();reader=CoreJournalReader(tmp_path,owner,'local')
    assert reader.read(selected) is None
    writer=JournalFixture(reader.path(selected),selected);writer.complete('one');reader.read(selected);writer.close()
    held=writer.path.with_suffix('.retained')
    try:writer.path.rename(held)
    except PermissionError as error:
        # A cached Windows SQLite handle denies replacement while open. After
        # explicit close, the independent disappearance guard still applies.
        assert error.winerror==32
        reader.close();writer.path.rename(held)
    with pytest.raises(JournalUnknown,match='DISAPPEARED'):reader.read(selected)
    reader.close()


@pytest.mark.parametrize('change',['intent','scope','rollback','session'])
def test_canonical_intent_drift_never_binds_other_work(tmp_path,change):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);selected=scope()
    reader=CanonicalIntentReader(tmp_path,home,server_id='server',actor_id='operator',pre_scope={k:selected[k] for k in tokens.PRE_SCOPE})
    fixture.admit('one',selected);reader.read('one')
    with sqlite3.connect(fixture.path) as db:
        if change=='intent':db.execute("UPDATE execution_client_intents SET resolved_json=json_set(resolved_json,'$.client_intent_id','other')")
        elif change=='scope':db.execute("UPDATE execution_client_intents SET resolved_json=json_set(resolved_json,'$.scope.binding_id','other')")
        elif change=='rollback':db.execute('DELETE FROM execution_client_intents')
        else:db.execute("UPDATE execution_sessions SET workspace_id='other'")
    with pytest.raises(JournalUnknown):reader.read('one')


def setup_journal(home,index,total):
    path=home/'connection-tests'/f'{index:032x}'/'journal.db';path.parent.mkdir(parents=True)
    journal=SQLiteJournal(path)
    selected=scope('setup')|{'server_id':'connection-test','executor_id':'local','session_id':'session'}
    for sequence,method in enumerate(('turn/started','thread/tokenUsage/updated','turn/completed'),1):
        value=event(sequence,method,total=total,op='turn',turn='setup-turn-'+str(index),
            thread='setup-thread-'+str(index),selected=selected,epoch='epoch');value.pop('received_at')
        asyncio.run(journal.append_event(RuntimeEvent(**value)))
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO operations_v2 VALUES('connection-test','local','turn','hash','session','SUCCEEDED',1,0,NULL,NULL)")
        db.execute("INSERT INTO operations_v2 VALUES('connection-test','local','close','hash','session','SUBMITTED',1,0,NULL,NULL)")
        db.execute("INSERT INTO owned_slot_reservations VALUES('connection-test','local','session','open',1)")
    return journal


def test_one_global_ledger_across_one_setup_local_continuation_reopen_remote_work(tmp_path):
    now=[1000.];home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home)
    control=create_control(tmp_path,lambda:now[0]);writers=[];setups=[];dispatches=[];stop=[]
    local=scope('local');remote=scope('connector')
    try:
        control.setup('setup-local','local',home,lambda:dispatches.append('setup-local'),lambda:stop.append('local'))
        setups.append(setup_journal(home,1,200));assert control.poll()['can_admit']
        flow,journal,stops=attach(control,fixture,tmp_path,home,selected=local)
        writers.append(JournalFixture(journal.path(local),local))
        for name,total in [('local-one',10),('local-two',20)]:
            control.start_work(name,'local','synthetic',binding=local,checkpoint=deepcopy(flow.document),
                stage='continuation' if name.endswith('two') else 'useful_work')
            consume(control);writers[0].complete(name,total,thread='local-native-thread');fixture.terminal(name,local)
            assert control.poll()['can_admit']
        first_hash=hashlib.sha256(control.path.read_bytes()).hexdigest()
        first_data=deepcopy(control.data);control.close()
        control=create_control(tmp_path,lambda:now[0],create=False)
        assert control.data==first_data and hashlib.sha256(control.path.read_bytes()).hexdigest()==first_hash
        flow,journal,stops=attach(control,fixture,tmp_path,home,selected=local)
        # Selected v11 remote bootstrap has zero productive model turns.
        assert control.poll()['can_admit']
        remote_flow,remote_reader,remote_stops=attach(control,fixture,tmp_path,home,'connector',remote)
        writers.append(JournalFixture(remote_reader.path(remote),remote))
        for name,total in [('remote-one',30),('remote-two',40)]:
            control.start_work(name,'connector','synthetic',binding=remote,checkpoint=deepcopy(remote_flow.document),
                stage='continuation' if name.endswith('two') else 'useful_work')
            consume(control);writers[1].complete(name,total,thread='remote-native-thread');fixture.terminal(name,remote)
            control.poll()
        summary=control.summary()
        assert summary['new_reserved_requests']==5 and summary['reserved_requests']==POLICY['max_cumulative_admissions']
        assert summary['known_observed_tokens']==POLICY['carry_in_tokens']+200+20+40
        assert summary['current']==[] and summary['reasons']==['GLOBAL_ALLOCATION_EXHAUSTED']
        assert dispatches==['setup-local']
        assert not stop and not remote_stops and not stops
        with pytest.raises(Refused):control.start_work('sixth','connector','forbidden',binding=remote,checkpoint=deepcopy(remote_flow.document))
        assert control.summary()['new_reserved_requests']==5
    finally:
        control.close()
        for writer in writers:writer.close()
        for journal in setups:journal.close()


def test_effect_boundary_checks_deadline_without_owner_tick(tmp_path):
    now=[1000.];home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home)
    control=create_control(tmp_path,lambda:now[0]);entered=threading.Event();release=threading.Event()
    flow,reader,stops=attach(control,fixture,tmp_path,home)
    original=flow.call
    def delayed(method,path,body=None):
        if method=='GET':entered.set();assert release.wait(2)
        return original(method,path,body)
    flow.call=delayed
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});assert entered.wait(1)
        now[0]=1121.;release.set()
        assert control.api.done.wait(1)
        assert not any(method=='POST' for method,_ in flow.calls)
        assert control.fence.event.is_set() and control.fence.reason=='DEADLINE120'
        consume(control)
        assert stops==['normal-stop'] and control.summary()['new_reserved_requests']==1
    finally:release.set();control.close()


def test_fresh_worker_validation_failure_never_posts(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);control=create_control(tmp_path)
    flow,reader,stops=attach(control,fixture,tmp_path,home)
    posts=[]
    def drift(method,path,body=None):
        if method=='GET':raise ConnectionError('PROFILE_DRIFT','Synthetic secret message not retained')
        posts.append(1)
    # Rewrap only this fake raw transport before any job starts.
    flow.call=control.api.transport(drift)
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});consume(control)
        assert posts==[] and stops==['normal-stop']
        text=control.path.read_text()
        assert 'Synthetic secret' not in text and 'PROFILE_DRIFT' in text
    finally:control.close()


def test_usage_counter_regression_latches_fault_without_reset(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);control=create_control(tmp_path)
    flow,reader,stops=attach(control,fixture,tmp_path,home);writer=None
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});consume(control)
        writer=JournalFixture(reader.path(flow.selected),flow.selected)
        writer.emit('turn/started','one');writer.emit('thread/tokenUsage/updated','one',100)
        assert control.poll()['known_observed_tokens']==(POLICY['carry_in_tokens']+100)
        writer.emit('thread/tokenUsage/updated','one',90)
        summary=control.poll()
        assert summary['known_observed_tokens']==(POLICY['carry_in_tokens']+100) and not summary['can_admit']
        assert 'USAGE_COUNTER_RESET_OR_REGRESSION' in control.accounting['faults'] and stops==['normal-stop']
    finally:
        control.close()
        if writer:writer.close()


def test_api_queue_and_cross_thread_controller_writes_are_refused(tmp_path):
    control=create_control(tmp_path);entered=threading.Event();release=threading.Event();errors=[]
    def held():entered.set();assert release.wait(2)
    try:
        control.schedule_read('held',held);assert entered.wait(1)
        with pytest.raises(JournalUnknown,match='ALREADY_IN_FLIGHT'):control.schedule_read('second',lambda:None)
        def wrong_owner():
            try:control.persist()
            except Exception as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=wrong_owner);thread.start();thread.join()
        assert errors==['Refused'] and control.api.started==1
    finally:release.set();consume(control);control.close()


def test_present_canonical_and_core_epoch_mismatch_blocks_usage(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);control=create_control(tmp_path)
    flow,reader,stops=attach(control,fixture,tmp_path,home);writer=None
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});consume(control)
        writer=JournalFixture(reader.path(flow.selected),flow.selected);writer.complete('one',100)
        fixture.terminal('one',flow.selected)
        with sqlite3.connect(fixture.path) as db:db.execute("UPDATE execution_sessions SET stream_epoch='other-epoch'")
        summary=control.poll()
        assert summary['known_observed_tokens']==POLICY['carry_in_tokens'] and not summary['can_admit']
        assert control.data['requests']['one']['first_observation_error']['reason']=='CANONICAL_CORE_EPOCH_MISMATCH'
        assert stops==['normal-stop']
    finally:
        control.close()
        if writer:writer.close()


def test_drain_accounts_late_usage_after_stop_wrapper_return_while_http_pending(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);control=create_control(tmp_path)
    entered=threading.Event();release=threading.Event();writer=None
    flow,reader,stops=attach(control,fixture,tmp_path,home,entered=entered,release=release)
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});assert entered.wait(1)
        control.fault('PRIMARY_SYNTHETIC_FAILURE');control.poll()
        assert stops==['normal-stop'] and control.api.thread.is_alive()
        writer=JournalFixture(reader.path(flow.selected),flow.selected)
        original=control.poll;ticks=[]
        def pumped():
            ticks.append(time.monotonic())
            if len(ticks)==3:
                writer.complete('one',90);fixture.terminal('one',flow.selected)
                release.set()
            return original()
        control.poll=pumped
        control.drain_api()
        assert len(ticks)>=3 and control.api.thread is None
        assert control.summary()['known_observed_tokens']==(POLICY['carry_in_tokens']+90)
        assert control.data['faults'][0]=='PRIMARY_SYNTHETIC_FAILURE'
        assert not control.summary()['can_admit'] and stops==['normal-stop']
        assert control.data['independent_observation']['worker_in_flight'] is False
        assert control.api_result['ok'] is True
        assert max(b-a for a,b in zip(ticks,ticks[1:]))<1
    finally:
        release.set();control.close()
        if writer:writer.close()


def test_historical_attachment_revalidates_owner_and_accounts_late_tokens(tmp_path):
    from history_observers import attach_existing_work
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);control=create_control(tmp_path)
    flow,reader,stops=attach(control,fixture,tmp_path,home);writer=None
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});consume(control)
        writer=JournalFixture(reader.path(flow.selected),flow.selected);writer.complete('one',10)
        fixture.terminal('one',flow.selected);control.poll();control.close()
        control=create_control(tmp_path,create=False)
        attached=attach_existing_work(control,campaign_root=tmp_path,server_home=home,
            connector_state=tmp_path/'connector-state',stop_for_lane=lambda lane:stops.append(lane))
        assert attached==['local']
        writer.emit('thread/tokenUsage/updated','one',25)
        assert control.poll()['known_observed_tokens']==(POLICY['carry_in_tokens']+25)
        with pytest.raises(Exception):
            attach_existing_work(control,campaign_root=tmp_path,server_home=tmp_path/'wrong-home',
                connector_state=tmp_path/'connector-state',stop_for_lane=lambda lane:None)
        assert control.summary()['new_reserved_requests']==1 and stops==[]
    finally:
        control.close()
        if writer:writer.close()
