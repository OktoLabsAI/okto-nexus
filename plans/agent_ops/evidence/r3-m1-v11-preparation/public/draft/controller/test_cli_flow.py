"""Installed parser/factory/TerminalWork with synthetic in-memory HTTP only."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json,time
import pytest

from test_independent import deny_external,scope
from cli_flow import CLIFlow
from api_worker import EffectFence,SerialAPI
from okto_nexus.adapters.inbound.cli import work as cli
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock,LockBusy
from okto_nexus.application.terminal_connection import ConnectionError,document_revision
from okto_nexus.application.terminal_work import TerminalWork


class HTTP:
    def __init__(self,root):
        self.root=root;self.selected=scope();self.calls=[];self.resolutions={};self.operations={};self.lost=None
        self.timeout=30;self.ready=True;self.inspections=0;self.decision=None
        key={k:self.selected[k] for k in ('server_id','executor_id','binding_id','agent_id','workspace_id','session_id')}
        key.update(canonical_request_id='approval',kind='permission')
        self.proposal={'approval_key':key,'recipient_agent_id':'operator','expected_revision':1,'request_hash':'hash',
                       'cas_token':'synthetic','expires_at':'2099-01-01T00:00:00Z','display':{'message':'Synthetic permission'}}
    def inspect(self):self.inspections+=1;return {'state':'ready' if self.ready else 'not_ready'}
    def operation(self,name):
        return {'operation_id':name,'scope':self.selected,'intent_hash':'intent-hash','executor_stage':'SUCCEEDED',
                'admission_state':'RESOLVED_TERMINAL','action':'turn.submit','result':{'output_text':'Synthetic result'}}
    def __call__(self,method,path,body=None):
        self.calls.append((method,path))
        if path.endswith('/connections/me'):return {'server_id':'server','agent_id':'operator'}
        if '/connections/setup/' in path:
            return {'connections':[self.selected|{'execution_location':'local','adapter_id':'codex_app_server'}],
                    'folders':{'workspace_root':str(self.root/'project')}}
        if '/connections/bindings/' in path:return dict(self.selected)
        if path.endswith('/runtime/intents:resolve'):
            request=body['client_intent_id'];initial=body['intent']=='runtime.start'
            value={'client_intent_id':request,'scope':self.selected,'operation_id':('open-' if initial else 'turn-')+request,
                   'resolution_revision':1,'intent_hash':'intent-hash','session_id':self.selected['session_id'],
                   'semantic_intent':{'action':'runtime.open' if initial else 'turn.submit'},'can_submit':True,'blockers':[]}
            self.resolutions[request]=value;return value
        if path.endswith('/runtime/operations'):
            request=body['client_intent_id'];value=self.operation(body['operation_id']);self.operations[request]=value
            if self.lost=='admission':self.lost=None;raise ConnectionError('OUTCOME_UNKNOWN','Synthetic lost admission',possible_effect=True,stage='m1_response_loss')
            return value
        if '/runtime/intents/' in path:
            request=path.rsplit('/',1)[-1]
            return {'resolution':self.resolutions[request],'operation':self.operations.get(request),
                    'initial_turn_operation_id':'turn-'+request}
        if '/runtime/operations/' in path:return self.operation(path.rsplit('/',1)[-1])
        if '/runtime/sessions/' in path:
            if '/events?' in path:return {'scope':self.selected,'events':[],'gap_pending':False,'has_more':False,'next_after_sequence':0}
            return {'scope':self.selected,'control_available':True,'lifecycle_state':'READY'}
        if '/runtime/sessions?' in path:return {'sessions':[],'has_more':False}
        if path.startswith('/api/v1/approvals?'):return {'data':{'items':[]}}
        if path=='/api/v1/approvals/approval':
            return {'data':{'approval_id':'approval','request_payload':{'kwargs':self.proposal},
                            'executed_result':self.decision,'status':'pending' if self.decision is None else 'resolved'}}
        if path.endswith('/runtime/approval-decisions'):
            self.decision={'decision_id':'decision','approval_key':body['approval_key'],'client_intent_id':body['client_intent_id'],
                           'request_hash':body['request_hash'],'canonical_state':'CONFIRMED','native_stage':'DELIVERED','actor_agent_id':'operator'}
            if self.lost=='decision':self.lost=None;raise ConnectionError('OUTCOME_UNKNOWN','Synthetic lost decision',possible_effect=True,stage='m1_response_loss')
            return self.decision
        if '/runtime/approval-decisions/' in path:return self.decision
        raise AssertionError('unplanned synthetic HTTP '+method+' '+path)


@pytest.fixture
def environment(tmp_path,monkeypatch):
    home=tmp_path/'home';(home/'terminal/profiles').mkdir(parents=True);(tmp_path/'project').mkdir()
    http=HTTP(tmp_path)
    connection={'state':'done','server_id':'server','selection':{'agent':http.selected['agent_id'],'client':'codex',
                 'project':str(tmp_path/'project'),'workspace_id':None,'candidate_ref':None,'provider_home':None},
                 'result':{'binding':http.selected}}
    (home/'terminal/profiles/project.json').write_text(json.dumps(connection))
    service=SimpleNamespace(adapter=SimpleNamespace(home=home),operator_http=http,inspect=http.inspect)
    monkeypatch.setattr(cli,'resolve_local_service',lambda args:service)
    flow=CLIFlow(service,'project',['--home',str(home)]);flow.expect(http.selected,'operator')
    fence=EffectFence();fence.arm(time.monotonic()+120);worker=SerialAPI(fence);flow.call=worker.transport(flow.call)
    def invoke(method,*args,**kwargs):
        worker.submit(method,lambda:getattr(flow,method)(*args,**kwargs),productive=method in ('submit','decide'))
        assert worker.done.wait(5)
        result=worker.take()
        if not result['ok']:raise result['error']
        return result['value']
    return SimpleNamespace(home=home,http=http,flow=flow,worker=worker,invoke=invoke,service=service)


def test_real_parser_factory_guard_handlers_display_and_reopen_continuation(environment,monkeypatch,capsys):
    e=environment;factory=cli.open_work;guarded=[]
    def spy(service,profile):
        other=ExclusiveFileLock(e.home/'terminal/profiles/project.guard')
        try:
            with pytest.raises(LockBusy):other.acquire()
        finally:other.release()
        flow=factory(service,profile);assert isinstance(flow,TerminalWork);guarded.append(True);return flow
    monkeypatch.setattr(cli,'open_work',spy)
    first=e.invoke('submit','Synthetic prompt',client_intent_id='first',new_session=True)
    assert first['operation_id']=='open-first'
    assert e.invoke('observe')['state']=='completed'
    e.invoke('events');assert 'events' in capsys.readouterr().out
    # A new factory/flow is created under the installed lock on each CLI command.
    second=e.invoke('submit','Synthetic continuation',client_intent_id='second')
    assert second['scope']['session_id']==first['scope']['session_id']
    assert len(guarded)==4 and e.http.inspections==4
    assert e.flow.diagnostics()['command_count']==4
    assert sum(method=='POST' and path.endswith('/runtime/operations') for method,path in e.http.calls)==2


def test_scope_changed_after_preflight_is_refused_under_cli_guard(environment):
    e=environment;e.http.selected['workspace_id']='changed'
    with pytest.raises(ConnectionError) as caught:e.invoke('submit','Synthetic',client_intent_id='one',new_session=True)
    assert caught.value.code=='CLI_SCOPE_CHANGED'
    assert not any(method=='POST' for method,path in e.http.calls)
    assert not e.flow.outcomes[-1]['handler_entered'] and e.flow.outcomes[-1]['exit_code']==3


@pytest.mark.parametrize('refusal',['readiness','lock'])
def test_cli_refusal_before_handler_does_not_post(environment,refusal,capsys):
    e=environment;lock=None
    if refusal=='readiness':e.http.ready=False
    else:lock=ExclusiveFileLock(e.home/'terminal/profiles/project.guard');lock.acquire()
    try:
        with pytest.raises(ConnectionError) as caught:e.invoke('submit','Synthetic',client_intent_id='one',new_session=True)
        assert caught.value.code=='CLI_NOT_DISPATCHED'
        assert not any(method=='POST' for method,path in e.http.calls)
        assert e.flow.outcomes[-1]['exit_code']==3 and not e.flow.outcomes[-1]['handler_entered']
        text=capsys.readouterr().out
        assert ('service_not_ready' if refusal=='readiness' else 'PROFILE_BUSY') in text
    finally:
        if lock:lock.release()


def test_lost_admission_exit3_preserves_error_and_status_recovery_never_posts(environment):
    e=environment;e.http.lost='admission'
    with pytest.raises(ConnectionError) as caught:e.invoke('submit','Synthetic',client_intent_id='one',new_session=True)
    assert caught.value.stage=='m1_response_loss'
    outcome=e.flow.outcomes[-1]
    assert outcome['exit_code']==3 and outcome['possible_effect'] and outcome['private_error'] is caught.value
    effects=sum(method=='POST' for method,path in e.http.calls)
    assert e.invoke('observe')['state']=='completed';e.invoke('events')
    assert sum(method=='POST' for method,path in e.http.calls)==effects


def test_answer_review_decision_and_lost_reply_recover_by_get_only(environment,capsys):
    e=environment;e.invoke('submit','Synthetic',client_intent_id='one',new_session=True)
    detail=e.invoke('decision_detail','approval');assert 'decision_review' in capsys.readouterr().out
    review=document_revision(detail['request_payload']['kwargs']);e.http.lost='decision'
    with pytest.raises(ConnectionError) as caught:e.invoke('decide','approval','approve',reviewed_revision=review)
    assert caught.value.possible_effect and e.flow.outcomes[-1]['exit_code']==3
    before=len(e.http.calls);detail=e.invoke('decision_detail','approval')
    assert detail['executed_result']['decision_id']=='decision'
    assert all(method=='GET' for method,path in e.http.calls[before:])
    assert sum(method=='POST' and path.endswith('/runtime/approval-decisions') for method,path in e.http.calls)==1


def test_presentation_exit3_does_not_promote_completed_handler(environment,monkeypatch):
    e=environment;original=cli.display;failed=[False]
    def display(value,*args,**kwargs):
        if not failed[0]:failed[0]=True;raise OSError('synthetic presentation error')
        return original(value,*args,**kwargs)
    monkeypatch.setattr(cli,'display',display)
    with pytest.raises(ConnectionError) as caught:e.invoke('submit','Synthetic',client_intent_id='one',new_session=True)
    assert caught.value.code=='CLI_OUTCOME_UNCONFIRMED' and caught.value.possible_effect
    assert e.flow.outcomes[-1]['possible_effect'] is True and e.flow.outcomes[-1]['private_error'] is caught.value
    assert e.flow.diagnostics()['recent'][-1]['error_type']=='ConnectionError'
    assert e.flow.outcomes[-1]['exit_code']==3 and e.flow.outcomes[-1]['handler_value']['operation_id']=='open-one'
    assert sum(method=='POST' and path.endswith('/runtime/operations') for method,path in e.http.calls)==1


def test_parser_rejection_keeps_original_systemexit_and_zero_effect(environment,capsys):
    e=environment
    with pytest.raises(SystemExit) as caught:e.invoke('submit',None,client_intent_id='one',new_session=True)
    assert caught.value.code==2 and not e.flow.outcomes[-1]['handler_entered']
    assert not any(method=='POST' for method,path in e.http.calls)
    assert 'error:' in capsys.readouterr().err


def test_remote_target_inspection_and_cli_decision_use_operator_client(environment,monkeypatch):
    from okto_nexus.adapters.inbound.cli import terminal_target as target
    from okto_nexus.application.terminal_connection import RemoteTerminalConnection
    e=environment;e.http.selected.update(adapter_id='codex_app_server',candidate_ref='candidate',state='APPROVED')
    path=e.home/'terminal/profiles/project.json';document=json.loads(path.read_text())
    document['selection']['operator_profile']='synthetic-human'
    document['remote_scope']={key:e.http.selected[key] for key in RemoteTerminalConnection.SCOPE}
    path.write_text(json.dumps(document));verified=[]
    e.http.base='http://synthetic.invalid'
    e.http.verify=lambda:verified.append(True) or e.http('GET','/api/v1/runtime-management/connections/me')
    monkeypatch.setattr(target,'OperatorProfile',lambda home,name:SimpleNamespace(client=lambda:e.http))
    def no_local_service(args):raise AssertionError('remote CLI selected local lifecycle')
    monkeypatch.setattr(cli,'resolve_local_service',no_local_service)
    e.invoke('submit','Synthetic remote',client_intent_id='remote-one',new_session=True)
    detail=e.invoke('decision_detail','approval')
    receipt=e.invoke('decide','approval','approve',reviewed_revision=document_revision(detail['request_payload']['kwargs']))
    assert receipt['actor_agent_id']=='operator' and receipt['canonical_state']=='CONFIRMED'
    assert e.invoke('observe')['state']=='completed'
    e.invoke('submit','Continue remotely',client_intent_id='remote-two')
    assert len(verified)==5
    assert sum(method=='POST' and path.endswith('/runtime/approval-decisions') for method,path in e.http.calls)==1


def test_events_exit_uses_displayed_page_while_status_keeps_failed_state(environment):
    e=environment;operation=e.http.operation
    e.http.operation=lambda name:operation(name)|{'executor_stage':'FAILED'}
    e.invoke('submit','Synthetic',client_intent_id='one',new_session=True)
    assert e.invoke('observe')['state']=='failed' and e.flow.outcomes[-1]['exit_code']==3
    page=e.invoke('events')
    assert page['state']=='failed' and 'events' in page
    assert e.flow.outcomes[-1]['exit_code']==0


def test_new_session_appearing_after_empty_preflight_is_refused(environment):
    e=environment;path=e.home/'terminal/work/project.json';path.parent.mkdir()
    path.write_text(json.dumps({'format':1,'session_id':'unexpected-session'}))
    with pytest.raises(ConnectionError) as caught:e.invoke('submit','Synthetic',client_intent_id='one',new_session=True)
    assert caught.value.code=='CLI_SCOPE_CHANGED'
    assert not any(method=='POST' for method,path in e.http.calls)
    assert not e.flow.outcomes[-1]['handler_entered']
