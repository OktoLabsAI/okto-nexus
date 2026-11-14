"""Installed TerminalWork pending-intent recovery with synthetic transport only."""
from copy import deepcopy
import pytest
from okto_nexus.application.terminal_connection import ConnectionError, document_revision
from okto_nexus.application.terminal_work import TerminalWork


@pytest.mark.parametrize('existing', [False, True])
def test_same_pending_intent_recovers_without_duplicate(existing):
    binding={key:key for key in ('server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id')}
    scope=dict(binding, session_id='new-session')
    request={'client_intent_id':'m1v14-local-work-01','agent_id':binding['agent_id'],
        'intent':'runtime.start','binding_id':binding['binding_id'],
        'workspace_binding_id':binding['workspace_binding_id'],'new_session':True,'text':'same fixture request'}
    context={k:v for k,v in request.items() if k!='text'}
    checkpoint={'format':1,'scope':binding,'session_id':'old-closed-session','work':{
        'client_intent_id':request['client_intent_id'],'request_hash':document_revision(request),
        'intent':'runtime.start','state':'resolve_submitted','has_text':True,'action':'send','request_context':context}}
    resolution={'client_intent_id':request['client_intent_id'],'scope':scope,'operation_id':'open',
        'resolution_revision':1,'intent_hash':'intent-hash','session_id':'new-session',
        'semantic_intent':{'action':'runtime.open'},'can_submit':True,'blockers':[]}
    operation={'operation_id':'open','scope':scope,'intent_hash':'intent-hash'}
    calls=[]; saved=[]
    def call(method,path,body=None):
        calls.append((method,path,deepcopy(body)))
        if method=='GET':
            if len(calls)==1 and not existing:
                raise ConnectionError('NOT_FOUND','Synthetic absent canonical intent.')
            return {'resolution':resolution,'operation':operation,'initial_turn_operation_id':'initial-turn'}
        if path.endswith('/runtime/intents:resolve'):
            assert body==request
            return resolution
        assert path.endswith('/runtime/operations')
        assert body['client_intent_id']==request['client_intent_id']
        return operation
    flow=TerminalWork(call,saved.append,{},checkpoint)
    flow.binding=lambda: binding
    result=flow.submit(request['text'],client_intent_id=request['client_intent_id'],new_session=True)
    posts=[(p,b) for m,p,b in calls if m=='POST']
    assert len(posts)==(0 if existing else 2)
    assert result['submission_turn_operation_id']=='initial-turn'
    assert flow.document['work']['client_intent_id']=='m1v14-local-work-01'
    assert checkpoint['work']['state']=='resolve_submitted'  # copied; no fixture reset


def test_pending_intent_changed_prompt_refuses_before_http():
    request={'client_intent_id':'same','new_session':True,'text':'original'}
    checkpoint={'work':{'client_intent_id':'same','request_hash':document_revision(request),
        'request_context':{'client_intent_id':'same','new_session':True},
        'state':'resolve_submitted','action':'send'}}
    flow=TerminalWork(lambda *args:pytest.fail('no HTTP after conflicting prompt'),lambda v:None,{},checkpoint)
    flow.binding=lambda:{}
    with pytest.raises(ConnectionError) as error:
        flow.submit('changed',client_intent_id='same',new_session=True)
    assert error.value.code=='WORK_REQUEST_CONFLICT'
