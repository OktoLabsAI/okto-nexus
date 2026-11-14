"""Fake lifecycle IO only; no scheduler/provider/process actions."""
import json
from types import SimpleNamespace as NS
import pytest
import run_case as R

def value(state='ready',reason=None,**change):
    return dict(state=state,reason=reason,instance_id='own',pid=123,generation='g',ready_for_queries=True,
        supervisor='windows-task-scheduler')|change

def test_pending_transport_then_ready_uses_get_only_bounded_observation():
    clock=[0];calls=[];records=[]
    sequence=iter([value('unknown','SERVICE_UNREACHABLE',pid=None,generation=None),value()])
    def inspect(timeout):calls.append(timeout);return next(sequence)
    ready=R.passive_ready(inspect,value('starting','SUPERVISOR_PENDING',pid=None,generation=None),'own',
        clock=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n),record=records.append)
    assert ready['state']=='ready' and calls==[1,1] and records[0]['post_count']==0

@pytest.mark.parametrize('state,reason',[('failed','SUPERVISOR_RETRY_EXHAUSTED'),('stopped','STARTUP_ABORTED'),
    ('unknown','SERVICE_DEFINITION_CHANGED'),('starting','CONCURRENT_LIFECYCLE')])
def test_positive_refusal_never_polled_or_restarted(state,reason):
    records=[]
    with pytest.raises(R.C.Refused,match='POSITIVE_START_REFUSAL'):
        R.passive_ready(lambda **k:pytest.fail('GET after refusal'),value(state,reason),'own',record=records.append)
    assert len(records[0]['observations'])==1

@pytest.mark.parametrize('change',[{'instance_id':'other'},{'pid':999},{'generation':'different'}])
def test_pending_owner_identity_never_reassigned(change):
    with pytest.raises(R.C.Refused):
        R.passive_ready(lambda **k:value(**change),value('starting','STARTUP_INCOMPLETE'),'own',sleep=lambda n:None)

def test_180_deadline_stays_finite_without_new_start():
    clock=[0];calls=[];records=[]
    def inspect(timeout):calls.append(timeout);return value('unknown','SERVICE_UNREACHABLE')
    with pytest.raises(R.C.Refused,match='PASSIVE_READY_DEADLINE'):
        R.passive_ready(inspect,value('unknown','SERVICE_UNREACHABLE'),'own',clock=lambda:clock[0],
            sleep=lambda n:clock.__setitem__(0,clock[0]+60),record=records.append)
    assert clock[0]==180 and len(calls)==2 and records[0]['post_count']==0

@pytest.mark.parametrize('problem',['none','missing_cohort','live_process','task_active','unconfirmed_drain'])
def test_uninstall_only_after_complete_cohort_exit_and_native_inactive(tmp_path,monkeypatch,problem):
    monkeypatch.setattr(R,'ROOT',tmp_path);monkeypatch.setattr(R,'PUBLIC',tmp_path)
    calls=[];trace=[]
    def cli(label):
        calls.append(label)
        return (0,{'state':'stopped','shutdown_outcome':'unconfirmed' if problem=='unconfirmed_drain' else 'drained'})
    def exits(handles,label):
        trace.append('all-physical-exits')
        if problem=='live_process':raise ValueError('SUPERVISOR_PHYSICAL_EXIT_UNCONFIRMED')
        return {'all':True}
    def inactive(service):
        trace.append('native-inactive')
        if problem=='task_active':raise ValueError('NATIVE_EXIT_UNCONFIRMED')
    monkeypatch.setattr(R.cohort,'wait_exits',exits);monkeypatch.setattr(R.cohort,'wait_native_inactive',inactive)
    monkeypatch.setattr(R.S,'inspect',lambda *a:{'state':'stopped'})
    monkeypatch.setattr(R.C,'retained_data',lambda *a:{'db':{'sha256':'same'}})
    service=NS(name='own',tasks=NS(read=lambda name:None));handles={k:object() for k in ('parent','launcher','runtime')}
    if problem=='missing_cohort':handles.pop('launcher')
    if problem=='none':
        assert R.wait_all_and_uninstall({},service,handles,cli)
        assert calls==['stop','uninstall'] and trace==['all-physical-exits','native-inactive']
    else:
        with pytest.raises((R.C.Refused,ValueError)):R.wait_all_and_uninstall({},service,handles,cli)
        assert calls==['stop'] and not (tmp_path/'cleanup.json').exists()

def test_setup_requires_exact_failed_auth_diagnostic_and_zero_replay():
    result={'test_id':'svc-t15-final-terminal-only-01','status':'failed','details':['PROVIDER_AUTH_REQUIRED'],
        'retryable_failure':True,'stage':'open'}
    assert R.C.validate_test(result)['error_code']=='PROVIDER_AUTH_REQUIRED'
    with pytest.raises(R.C.Refused):R.C.validate_test(result|{'status':'passed'})

def test_no_termination_access_exists_in_candidate_support():
    text=R.S.Path(R.S.__file__).read_text()
    assert "TERMINATION_RIGHT_REFUSED" in text and '0x0001' not in text and 'TerminateProcess' not in text

def test_live_cli_timeout_prohibits_parallel_cleanup(monkeypatch):
    monkeypatch.setattr(R.S,'CHILDREN',[NS(poll=lambda:None)])
    with pytest.raises(R.C.Refused,match='CLI_STILL_RUNNING_NO_PARALLEL_CLEANUP'):
        R.wait_all_and_uninstall({},None,{},lambda label:pytest.fail('parallel CLI forbidden'))

@pytest.mark.parametrize('image,pinned',[('foreign.exe',True),('pythonw.exe',False),('pythonw.exe',True)])
def test_runtime_image_is_bound_before_cohort_or_setup(monkeypatch,image,pinned):
    plan={'instance_ids':{'nexus':'own'},'python_images':{image:'approved'} if pinned else {}}
    owner=NS(image=image,identity={'pid':123,'generation':'g','instance_id':'own'})
    monkeypatch.setattr(R.S,'Owner',lambda *a,**k:owner)
    monkeypatch.setattr(R.C,'sha',lambda path:'changed')
    monkeypatch.setattr(R.cohort,'capture_cycle',lambda *a:pytest.fail('invalid runtime image'))
    with pytest.raises(R.C.Refused,match='RUNTIME_IMAGE_CHANGED'):
        R.capture_ready_cohort(plan,None,value(),lambda **k:value())

def test_empty_cohort_stopped_task_absent_is_not_physical_exit_proof(tmp_path,monkeypatch):
    monkeypatch.setattr(R,'PUBLIC',tmp_path);clock=[0]
    monkeypatch.setattr(R.S,'inspect',lambda *a:{'state':'stopped','pid':None,'instance_id':'own'})
    monkeypatch.setattr(R.cohort,'failure_handoff',lambda **k:pytest.fail('empty handles must not pass'))
    service=NS(name='own-task',tasks=NS(read=lambda name:None))
    R.handoff({},service,{},seconds=5,clock=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n))
    proof=json.loads((tmp_path/'uncaptured-handoff-final.json').read_bytes())
    assert proof['status']=='UNKNOWN_OBSERVER_EXPIRED' and not proof['physical_exit_proven']
    assert proof['last']['native']['present'] is False and proof['cleanup_confirmed'] is False

def test_handoff_later_ready_captures_without_service_actions(tmp_path,monkeypatch):
    monkeypatch.setattr(R,'PUBLIC',tmp_path)
    monkeypatch.setattr(R.S,'inspect',lambda *a:value())
    acquired={k:object() for k in ('runtime','launcher','parent')};calls=[]
    monkeypatch.setattr(R,'capture_ready_cohort',lambda *a:(None,{'same':'native'},acquired,{'same':'cycle'}))
    monkeypatch.setattr(R.cohort,'failure_handoff',lambda **k:calls.append(k))
    R.handoff({},NS(name='own',tasks=NS(read=lambda n:NS(state=4,active=True))),{},seconds=5,clock=lambda:0)
    proof=json.loads((tmp_path/'handoff-cohort-acquired.json').read_bytes())
    assert calls==[{'seconds':5}] and proof['query_only'] and proof['cleanup_confirmed'] is False
