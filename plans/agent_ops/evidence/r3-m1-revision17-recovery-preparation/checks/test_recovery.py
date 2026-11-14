from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import json,sys
import pytest
H=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(H),str(H/'modules')]
import request_context as cm

@pytest.fixture(scope='module')
def context():
    path=H/'amendment.json'
    return cm.gate(SimpleNamespace(amendment=str(path),expected_amendment_sha256=cm.sha(path)))

@pytest.fixture
def prior(context,tmp_path):
    pin=context.P['adoption']['predecessor_work_checkpoint_pin']
    data=Path(pin['path']).read_bytes()
    (tmp_path/'predecessor-work-checkpoint.json').write_bytes(data)
    return SimpleNamespace(PRIVATE=tmp_path,P=context.P),json.loads(data)['authorization']

def test_recovery_gate_same_policy_ids_five_paid_histories(context):
    from fresh_work_controller import prepare_derived
    from close_campaign import checkpoint_summary
    import token_collector
    a=context.amendment;old=json.loads((H.with_name('work-revision17')/'amendment.json').read_bytes())
    assert a['policy']==old['policy'] and a['request_ids']==old['request_ids']
    assert a['basis']['checkpoint']==old['basis']['checkpoint'] and a['basis']['companion']==old['basis']['companion']
    assert context.P['finite_work']['request']==old['prompt_revision']['request']
    cp=prepare_derived(*[json.loads(cm.pinned(a['basis'][k]).read_bytes()) for k in ('checkpoint','companion','accounting')],source_pins=a['basis'])
    assert cp['requests']=={} and cp['fresh_local_work']['historical_record_count']==5
    assert cp['fresh_local_work']['source_pins']['operational_preflight']==a['closed_preflight']
    summary=checkpoint_summary(context,cp,token_collector.summary(token_collector.restore(cp['collector'])))
    assert summary['cumulative_minimum_observed_tokens']==460793 and summary['cumulative_reserved_admissions']==14
    assert not any((H/n).exists() for n in ('public','private','runtime-private','package'))

def test_exact_pinned_review_refreshes_via_actual_installed_canonical_method(prior):
    from authorize_local import validate_prior_review,bounded_transport
    from okto_nexus.application.terminal_authorization import TerminalAuthorization
    from okto_nexus.application.terminal_work import TerminalWork
    from okto_nexus.application.terminal_connection import document_revision
    context,pending=prior
    assert validate_prior_review(context,pending)
    calls=[];counts={};saved=[]
    class Flow(TerminalAuthorization):
        api=TerminalWork.api
        def __init__(self):
            self.document={'authorization':deepcopy(pending)}
            self.call=bounded_transport(self.transport,'review',counts)
        def binding(self):return dict(context.P['adoption']['expected_scope'])
        def _check_scope(self,scope,binding):assert scope==pending['review']['scope']
        def _save(self):saved.append(deepcopy(self.document))
        def authorize(self,**kwargs):pytest.fail('Uncertain issuance recovery entered')
        def transport(self,method,path,body=None):
            calls.append((method,path,deepcopy(body)))
            assert method=='POST' and path.endswith('/connections/authorizations:review')
            assert body['client_request_id']!=pending['review']['request']['client_request_id']
            result=deepcopy(pending['review']);result['can_issue']=True
            for grant in result['current_grants']:grant['state']='expired'
            result['request']={**result['request'],'client_request_id':body['client_request_id']}
            return result
    flow=Flow();result=flow.authorization_review(minutes=60,max_executions=3)
    assert counts=={'review':1} and len(calls)==1 and len(saved)==1
    assert result['review_revision']==document_revision(flow.document['authorization']['review'])
    assert flow.document['authorization']['state']=='review'
    assert result['review_revision']!=pending['review_revision']
    assert len(saved)==1  # only canonical method wrote its in-memory checkpoint fixture

@pytest.mark.parametrize('state',['submitted','unknown'])
def test_submitted_or_unknown_refused_before_canonical_transport(prior,state):
    from authorize_local import validate_prior_review,Refused
    context,pending=prior;pending['state']=state
    with pytest.raises(Refused,match='PRIOR_AUTHORIZATION_SELECTION_PRESENT'):validate_prior_review(context,pending)

def test_tampered_historical_review_refused(prior):
    from authorize_local import validate_prior_review,Refused
    context,pending=prior;pending['review']['scope']['agent_id']='different-agent'
    with pytest.raises(Refused,match='PINNED_HISTORICAL_REVIEW_REQUIRED'):validate_prior_review(context,pending)

def test_operational_predecessor_cannot_gain_a_model_reservation(context,tmp_path):
    from legacy_controller import seal
    proof=json.loads(cm.pinned(context.amendment['closed_preflight']).read_bytes())
    cp=json.loads(cm.pinned(proof['files']['checkpoint']).read_bytes())
    cp['requests']['m1v17-local-useful-15']={'kind':'work'};cp['state_sha256']=seal(cp)
    path=tmp_path/'changed.json';path.write_text(json.dumps(cp))
    proof['files']['checkpoint']={'path':str(path),'sha256':cm.sha(path)}
    path=tmp_path/'proof.json';path.write_text(json.dumps(proof))
    with pytest.raises(RuntimeError,match='OPERATIONAL_PREDECESSOR_REQUESTS_OR_FAULTS_CHANGED'):
        cm.verify_closed_preflight({'path':str(path),'sha256':cm.sha(path)})
