from copy import deepcopy
import ast,json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
import pytest
from test_independent import create_control,attach,CanonicalFixture,consume,Refused
from test_cli_flow import environment
from response_loss import CampaignState,FiniteResponseLoss,DriverRefusal
from okto_nexus.application.terminal_connection import document_revision,PREFIX

def test_first_work_explicitly_opens_new_session_after_old_checkpoint(tmp_path):
    home=tmp_path/'home';home.mkdir();fixture=CanonicalFixture(home)
    controller=create_control(tmp_path)
    flow,_,_=attach(controller,fixture,tmp_path,home)
    old={'session_id':'closed-predecessor','work':{'client_intent_id':'historical'}}
    try:
        with pytest.raises(Refused,match='SESSION_NOT_OWNED_BY_CONTROLLER'):
            controller.start_work('new','local','synthetic',binding=flow.selected,checkpoint=old)
        controller.start_work('new','local','synthetic',binding=flow.selected,checkpoint=old,new_session=True)
        result=consume(controller)
        assert result['ok'] and controller.data['requests']['new']['stream'] is None
        assert old=={'session_id':'closed-predecessor','work':{'client_intent_id':'historical'}}
        assert controller.summary()['reserved_requests']==10
    finally:controller.close()

def test_installed_cli_new_session_rebinds_expected_session_then_observes(environment):
    e=environment;path=e.home/'terminal/work/project.json';path.parent.mkdir(exist_ok=True)
    old={'format':1,'session_id':'closed-predecessor'}
    path.write_text(json.dumps(old))
    e.flow.expected_session='closed-predecessor'
    result=e.invoke('submit','Synthetic new session',client_intent_id='successor',new_session=True)
    assert result['operation_id']=='open-successor'
    assert e.flow.expected_session==e.http.selected['session_id']!='closed-predecessor'
    assert e.invoke('observe')['state']=='completed'

def test_three_exact_decisions_per_lane_and_fourth_denied_before_http(tmp_path):
    state=CampaignState(tmp_path/'response.json',campaign_id='synthetic14');calls=[]
    scope={'server_id':'server','executor_id':'executor','binding_id':'binding','agent_id':'agent','workspace_id':'workspace'}
    checkpoint={'scope':scope,'session_id':'session'}
    def http(method,path,body):
        calls.append(body)
        return {'canonical_state':'CONFIRMED','decision_id':'decision-'+body['client_intent_id'],
            'approval_key':body['approval_key'],'request_hash':body['request_hash'],'client_intent_id':body['client_intent_id']}
    for lane in ('local','connector'):
        transport=FiniteResponseLoss(http,lambda:checkpoint,state,lane)
        for number in range(4):
            body={'client_intent_id':lane+str(number),'request_hash':'hash',
                'approval_key':scope|{'session_id':'session','canonical_request_id':lane+str(number)},'response':{'decision':'approve'}}
            checkpoint['decision']={k:v for k,v in body.items() if k!='response'}
            checkpoint['decision']['response_hash']=document_revision(body['response'])
            if number<3:transport('POST',PREFIX+'/runtime/approval-decisions',body)
            else:
                before=len(calls)
                with pytest.raises(DriverRefusal,match='DECISION_ALLOCATION_EXHAUSTED'):
                    transport('POST',PREFIX+'/runtime/approval-decisions',body)
                assert len(calls)==before
    assert len(calls)==6 and len(CampaignState(tmp_path/'response.json').data['decisions'])==6

def test_two_decisions_recover_each_exact_saved_checkpoint(tmp_path):
    source=Path(__file__).parent.parent/'m1_v14_work.py'
    tree=ast.parse(source.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='recover_decisions')
    receipts={};details={};written=[]
    for key in ('first','second'):
        metadata={'approval_key':{'canonical_request_id':key,'session_id':'session'},'request_hash':'hash-'+key,'client_intent_id':'intent-'+key}
        (tmp_path/(key+'-decision-checkpoint.json')).write_text(json.dumps(metadata))
        receipts['decision-'+key]=metadata|{'decision_id':'decision-'+key,'canonical_state':'CONFIRMED'}
        details[key]={'executed_result':{'decision_id':'decision-'+key}}
    flow=SimpleNamespace(decision_detail=lambda key,**kw:details[key],api=lambda method,path:receipts[path.rsplit('/',1)[-1]])
    env={'X':SimpleNamespace(PRIVATE=tmp_path),'selected_decisions':{'first','second'},'recovered_decisions':{},
         'json':json,'quote':quote,'public_write':lambda name,value:written.append(name)}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),env)
    env['recover_decisions'](flow)
    assert set(env['recovered_decisions'])=={'first','second'} and len(written)==2
