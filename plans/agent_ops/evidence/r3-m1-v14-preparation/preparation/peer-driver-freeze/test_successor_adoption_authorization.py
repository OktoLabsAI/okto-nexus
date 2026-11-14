"""Own synthetic fixtures only; installed parser/authorization, never a service."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import json
import socket
import subprocess
import sys
import threading
import asyncio  # Windows imports subclass Popen before the no-effects fixture replaces it.
import pytest
import driver_common as common
import adopt_local as adopt
import authorize_local as auth
from test_drivers import context
from test_operator_bootstrap import owner

@pytest.fixture(autouse=True)
def no_effects(monkeypatch):
    def refuse(*_a, **_k):raise AssertionError('REAL EFFECT FORBIDDEN')
    monkeypatch.setattr(subprocess, 'Popen', refuse); monkeypatch.setattr(socket, 'socket', refuse)

def put(path, value):path.write_text(json.dumps(value),encoding='utf-8')

@pytest.fixture
def adopted(context):
    c=context
    scope={k:'fixture-'+k for k in (*auth.SCOPE,'adapter_id','candidate_ref')}
    c.P['adoption']={'expected_scope':scope,'setup_client_intent_id':'fixture-setup'}
    payloads={'profile_pin':{'state':'done','version_check_confirmed':True,
        'request':{'client_intent_id':'fixture-setup'},'result':{'binding':scope}},
        'setup_result_pin':{'cli_exit':0,'reported_state':'configured'},
        'predecessor_closure_pin':{},'predecessor_checkpoint_pin':{},'installation_result_pin':{},
        'predecessor_original_checkpoint_pin':{},'predecessor_companion_pin':{},
        'predecessor_work_checkpoint_pin':{'session_id':'prior-session','authorization':{'state':'done'}}}
    for key,value in payloads.items():
        p=c.ROOT/(key+'.json');put(p,value);c.P['adoption'][key]={'path':str(p),'sha256':common.sha(p)}
    common.public_save(c,'root-driver-preparation.json',{'status':'fixture'})
    return c

def test_adoption_is_get_only_then_new_zero_reservation_checkpoint(adopted):
    c=adopted;events=[];scope=c.P['adoption']['expected_scope']
    flow=SimpleNamespace(binding=lambda: events.append('GET binding') or dict(scope,state='APPROVED'),
        api=lambda m,p:events.append((m,p)) or {'server_id':scope['server_id']})
    def construct(*,create):
        assert create and events==['GET binding',('GET','/connections/me')]
        assert (c.PRIVATE/'predecessor-work-checkpoint.json').read_bytes()==Path(c.P['adoption']['predecessor_work_checkpoint_pin']['path']).read_bytes()
        events.append('new controller')
        return SimpleNamespace(data={'requests':{}},summary=lambda:{'known_observed_tokens':134199},close=lambda:events.append('closed'))
    c.controller=construct
    result=adopt.adopt(c,observe=owner,flow_factory=lambda _:flow)
    assert result['model_admissions']==0 and result['setup_replayed'] is False and events[-1]=='closed'
    with pytest.raises(FileExistsError):adopt.adopt(c,observe=owner,flow_factory=lambda _:flow)

@pytest.mark.parametrize('change',['pin','configured','scope','intent'])
def test_adoption_rejects_changed_sources_before_controller(adopted,change):
    c=adopted;p=Path(c.P['adoption']['profile_pin']['path']);value=json.loads(p.read_text())
    if change=='configured':value['state']='test_submitted'
    if change=='scope':value['result']['binding']['executor_id']='foreign'
    if change=='intent':value['request']['client_intent_id']='foreign'
    put(p,value)
    if change!='pin':c.P['adoption']['profile_pin']['sha256']=common.sha(p)
    else:p.write_text(p.read_text()+' ')
    c.controller=lambda **_:pytest.fail('controller must not be created')
    with pytest.raises(common.Refused):adopt.adopt(c,observe=owner,flow_factory=lambda _:pytest.fail('no HTTP'))

@pytest.fixture
def review(adopted):
    scope=adopted.P['adoption']['expected_scope']
    adopted.P['adoption']['expected_historical_grants']=[
        {'grant_id':'original','revision':1,'expires_at':'2020-01-01T00:00:00Z','max_executions':20,'minimum_used_executions':0},
        {'grant_id':'used','revision':1,'expires_at':'2030-01-01T01:00:00Z','max_executions':20,'minimum_used_executions':1}]
    return {'state':'authorization_review','scope':{k:scope[k] for k in auth.SCOPE},
        'current_grants':[dict({k:v for k,v in g.items() if k!='minimum_used_executions'},
            state='expired',used_executions=g['minimum_used_executions'],actions=sorted(auth.ACTIONS))
            for g in adopted.P['adoption']['expected_historical_grants']],
        'can_issue':True,'total_grants':2,'has_more_grants':False,'actions':sorted(auth.ACTIONS),
        'request':{'binding_id':scope['binding_id'],'client_request_id':'fixture-grant',
            'expected_revision':'sha256:fixture','expires_at':'2030-01-01T01:00:00Z','max_executions':3},
        'review_revision':'fixture-revision'}

@pytest.mark.parametrize('state',['revoked','superseded','exhausted','available'])
def test_apply_refuses_nonexpired_original(adopted,review,state):
    review['current_grants'][0]['state']=state
    with pytest.raises(common.Refused):auth.validate_review(adopted,review)

@pytest.mark.parametrize('change',['used','max','actions','scope','more','second','cas'])
def test_review_refuses_scope_limits_or_ambiguous_history(adopted,review,change):
    if change=='used':review['current_grants'][1]['used_executions']=0
    if change=='max':review['current_grants'][0]['max_executions']=21
    if change=='actions':review['actions'].append('execute_work')
    if change=='scope':review['scope']['workspace_id']='other'
    if change=='more':review['has_more_grants']=True
    if change=='second':review['current_grants'].append(deepcopy(review['current_grants'][0]))
    if change=='cas':review['request']['expected_revision']=''
    with pytest.raises(common.Refused):auth.validate_review(adopted,review)

def test_available_review_is_not_failure_but_never_issues(adopted,review):
    review['current_grants'][1]['state']='available';review['can_issue']=False
    assert auth.validate_review(adopted,review,allow_available=True)=='used'
    with pytest.raises(common.Refused):auth.validate_review(adopted,review)

@pytest.mark.parametrize('change',['unknown','duplicate','revision','expiry','used_bool','used_reset','used_excess','balance','two_available','can_issue'])
def test_v14_preserves_exact_history_and_consumption(adopted,review,change):
    grants=review['current_grants'];grants[1]['state']='available';review['can_issue']=False
    if change=='unknown':grants[0]['grant_id']='unknown'
    if change=='duplicate':grants[0]=deepcopy(grants[1])
    if change=='revision':grants[1]['revision']=2
    if change=='expiry':grants[1]['expires_at']='2040-01-01T00:00:00Z'
    if change=='used_bool':grants[1]['used_executions']=True
    if change=='used_reset':grants[1]['used_executions']=0
    if change=='used_excess':grants[1]['used_executions']=21
    if change=='balance':grants[1]['used_executions']=18
    if change=='two_available':grants[0]['state']='available'
    if change=='can_issue':review['can_issue']=True
    with pytest.raises(common.Refused):auth.validate_review(adopted,review,allow_available=True)

def test_v14_three_remaining_actions_and_expired_used_history(adopted,review):
    review['current_grants'][1].update(state='available',used_executions=17);review['can_issue']=False
    assert auth.validate_review(adopted,review,allow_available=True)=='used'
    review['current_grants'][1]['state']='expired';review['can_issue']=True
    assert auth.validate_review(adopted,review) is None
    assert review['request']['max_executions']==3

@pytest.mark.parametrize('name',['predecessor_companion_pin','predecessor_original_checkpoint_pin','predecessor_work_checkpoint_pin'])
def test_v14_ancestry_drift_refuses_before_new_controller(adopted,name):
    Path(adopted.P['adoption'][name]['path']).write_text('changed')
    adopted.controller=lambda **_:pytest.fail('no controller')
    with pytest.raises(common.Refused,match='ADOPTION_SOURCE_CHANGED'):
        adopt.adopt(adopted,observe=owner,flow_factory=lambda _:pytest.fail('no GET'))

def test_v14_publication_import_uses_declared_sibling_without_inherited_path(adopted,monkeypatch):
    base=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/draft')
    adopted.modules=base/'controller'
    adopted.P['execution_bundle']['files']['publication']={'path':str(base/'publication.py')}
    common.public_save(adopted,'adopt-local-result.json',{'status':'fixture'})
    monkeypatch.setattr(auth,'status',owner)
    monkeypatch.setattr(sys,'path',[p for p in sys.path if str(base).lower() not in str(p).replace('\\','/').lower()])
    monkeypatch.delitem(sys.modules,'publication',raising=False)
    class ImportComplete(Exception):pass
    def stop(*,create):raise ImportComplete()
    adopted.controller=stop
    with pytest.raises(ImportComplete):auth.execute(adopted,'review')
    assert Path(sys.modules['publication'].__file__).resolve()==(base/'publication.py').resolve()

def test_transport_blocks_every_model_and_repeated_authorization_effect(review):
    calls=[]; counts={};request=review['request']
    transport=auth.bounded_transport(lambda *a:calls.append(a), 'apply',counts,expected_request=request)
    with pytest.raises(common.Refused):transport('POST',auth.PREFIX+'/runtime/operations',{})
    transport('POST',auth.PREFIX+'/connections/authorizations:recover',request)
    transport('POST',auth.PREFIX+'/connections/authorizations:issue',request)
    with pytest.raises(common.Refused):transport('POST',auth.PREFIX+'/connections/authorizations:issue',request)
    assert len(calls)==2 and counts=={'recover':1,'issue':1}

def test_lost_issue_consumes_effect(review):
    def lost(*_):raise OSError('fixture lost response')
    counts={};call=auth.bounded_transport(lost,'apply',counts,expected_request=review['request'])
    with pytest.raises(OSError):call('POST',auth.PREFIX+'/connections/authorizations:issue',review['request'])
    with pytest.raises(common.Refused):call('POST',auth.PREFIX+'/connections/authorizations:issue',review['request'])

@pytest.mark.parametrize('kind',['available','replaced'])
def test_local_work_uses_verified_grant_and_current_window(adopted,review,kind):
    c=adopted;now=datetime(2030,1,1,tzinfo=timezone.utc)
    common.public_save(c,'adopt-local-result.json',{'status':'CONFIGURED_PREDECESSOR_ADOPTED','scope':c.P['adoption']['expected_scope']})
    if kind=='available':
        review['current_grants'][1].update(state='available');review['can_issue']=False
    rp=common.public_save(c,'authorize-local-review.json',{'status':'EXISTING_GRANT_AVAILABLE' if kind=='available' else 'EXPIRED_GRANTS_REVIEWED','review':review,'work_checkpoint_sha256':'a'*64})
    if kind=='replaced':
        common.public_save(c,'authorize-local-apply.json',{'status':'EXPIRED_GRANT_REPLACEMENT_CONFIRMED','work_checkpoint_sha256':'b'*64,
            'review_revision':review['review_revision'],'review_sha256':common.sha(rp),
            'client_request_id':review['request']['client_request_id'],
            'grant':{'expires_at':review['request']['expires_at'],'max_executions':3,'actions':sorted(auth.ACTIONS)}})
    assert auth.require_local_work_authorization(c,now=now)['remaining_seconds_by_local_clock']==3600
    assert auth.require_local_work_authorization(c,now=now)['work_checkpoint_sha256']==('a' if kind=='available' else 'b')*64
    with pytest.raises(common.Refused,match='WINDOW_INSUFFICIENT'):
        auth.require_local_work_authorization(c,now=now+timedelta(seconds=2971))
    assert auth.require_local_work_authorization(c,now=now+timedelta(seconds=2970))['minimum_window_seconds']==630

@pytest.mark.parametrize('prior_done',[False,True])
def test_installed_parser_and_handlers_review_then_single_cas_issue(adopted,review,monkeypatch,prior_done):
    # Actual installed run_work/parser/TerminalAuthorization and CLIFlow worker;
    # only topology and HTTP are fixtures. No provider, real controller or service.
    modules=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/draft/controller')
    monkeypatch.syspath_prepend(str(modules))
    from cli_flow import CLIFlow
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.inbound.cli import terminal_target
    from okto_nexus.application.terminal_work import TerminalWork
    from okto_nexus.application.terminal_connection import ConnectionError, document_revision
    c=adopted;scope=c.P['adoption']['expected_scope'];home=c.ROOT/'server';profile='fixture'
    target=home/'terminal/profiles'/('fixture.json');target.parent.mkdir(parents=True);put(target,{})
    service=SimpleNamespace(adapter=SimpleNamespace(home=home),inspect=lambda:{'state':'ready'})
    monkeypatch.setattr(terminal_target,'terminal_target_selection',lambda *_:(home,None))
    monkeypatch.setattr(terminal_target,'resolve_terminal_target',lambda *_:service)
    state={'checkpoint':{'authorization':{'state':'done'}}} if prior_done else {}
    calls=[];phase=['review'];counts={}
    raw_review={k:v for k,v in review.items() if k!='review_revision'}
    def raw(method,path,body=None):
        calls.append((method,path,deepcopy(body)))
        if method=='GET':return {'server_id':scope['server_id'],'agent_id':'fixture-operator'}
        name=path.split(':')[-1]
        if name=='review':
            result=deepcopy(raw_review);result['request']['client_request_id']=body['client_request_id'];return result
        if name=='recover':raise ConnectionError('NOT_FOUND','fixture',stage='connection.authorization')
        assert name=='issue'
        grant=dict(grant_id='replacement',actor_agent_id=scope['agent_id'],represented_agent_id=scope['agent_id'],
            endpoint_id=scope['endpoint_id'],workspace_id=scope['workspace_id'],expires_at=body['expires_at'],
            max_executions=3,actions=sorted(auth.ACTIONS))
        return {'state':'authorization_committed','client_request_id':body['client_request_id'],
            'request_hash':'sha256:'+document_revision(body),'result':{'scope':{k:scope[k] for k in auth.SCOPE},'grant':grant}}
    def factory(*_args,**_kwargs):
        flow=TerminalWork(raw,lambda value:state.update(checkpoint=value),
            {'server_id':scope['server_id'],'selection':{'agent':scope['agent_id']},'result':{'binding':scope}},state.get('checkpoint'))
        flow.binding=lambda:dict(scope,state='APPROVED')
        return flow
    monkeypatch.setattr(cli,'open_work',factory)
    flow=CLIFlow(service,profile,[]);flow.expect(scope,'fixture-operator')
    output={}
    def run(phase,options,handler):
        transport=flow.call
        flow.call=auth.bounded_transport(transport,phase,counts,
            expected_request=state.get('checkpoint',{}).get('authorization',{}).get('review',{}).get('request'))
        def worker():
            try:output[phase]=flow._execute('authorize',options,handler)
            except BaseException as error:output[phase]=error
        thread=threading.Thread(target=worker);thread.start();thread.join()
        flow.call=transport
        assert not isinstance(output[phase],BaseException),type(output[phase]).__name__
    run('review',['--minutes','60','--actions','3'],'authorization_review')
    auth.validate_review(c,output['review'])
    run('apply',['--review',output['review']['review_revision']],'authorize')
    assert state['checkpoint']['authorization']['state']=='done'
    assert counts=={'review':1,'recover':1,'issue':1}
    assert flow.diagnostics()['entrypoint']=='INSTALLED_RUN_WORK_PARSER_AND_HANDLERS'
    assert [x['action'] for x in flow.outcomes]==['authorize','authorize']
    assert all(x[0]=='GET' or '/connections/authorizations:' in x[1] for x in calls)
