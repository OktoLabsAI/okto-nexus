"""Offline finite gate/cohort tests. No Scheduler, HTTP, process, provider or private DB."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util,json,sys
import pytest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import request_context as ctx
import cohort
import driver_common as common

def identity(pid=1):
    return {'pid':pid,'generation':'gen','instance_id':'svc','component':'nexus',
        'task':{'name':'task','digest':'digest','state':4}}

def cycle():
    return {'cycle_id':'cycle','phase':'running','attempts_started':1,'child_acknowledged':True,
        'parent':{'pid':2,'birth':20},'launcher':{'pid':3,'birth':30},'child':{'pid':1,'birth':10}}

@pytest.mark.parametrize('code,state,reason,timed,accepted',[
    (0,'ready',None,None,True),(3,'unknown','SERVICE_UNREACHABLE',True,True),
    (3,'starting','SUPERVISOR_PENDING',True,True),(3,'starting','SUPERVISOR_BACKOFF',True,False),
    (3,'starting','SUPERVISOR_LAST_ATTEMPT_FAILED',True,False),
    (3,'failed','SERVICE_SUPERVISION_POLICY_CHANGED',True,False),(3,'unknown',None,True,False),
    (3,'starting','SUPERVISOR_PENDING',False,False)])
def test_passive_timeout_is_not_positive_failure(code,state,reason,timed,accepted):
    value={'component':'nexus','action':'start','returncode':code,'reported_state':state,
        'reported_reason':reason,'wait_timed_out':timed}
    if accepted:cohort.allow_passive_observation(value)
    else:
        with pytest.raises(Exception):cohort.allow_passive_observation(value)

def test_partial_capture_closes_every_handle(tmp_path,monkeypatch):
    image=tmp_path/'image';image.write_bytes(b'fixture')
    context=SimpleNamespace(installed={'python_images':{str(image):ctx.sha(image)}})
    made=[]
    class Handle:
        def __init__(self,pid):
            if pid==3:raise ValueError('partial')
            self.birth=20;self.image=str(image);self.closed=False;made.append(self)
        def close(self):self.closed=True
        def exited(self):return False
    with pytest.raises(ValueError,match='partial'):
        cohort.capture(context,observe=lambda *_:identity(),read_cycle=lambda *_:cycle(),process=Handle)
    assert len(made)==1 and made[0].closed

def test_capture_rejects_cycle_drift_and_closes(tmp_path):
    image=tmp_path/'image';image.write_bytes(b'fixture')
    context=SimpleNamespace(installed={'python_images':{str(image):ctx.sha(image)}})
    made=[];reads=0
    class Handle:
        def __init__(self,pid):self.birth=pid*10;self.image=str(image);self.closed=False;made.append(self)
        def close(self):self.closed=True
        def exited(self):return False
    def read(_):
        nonlocal reads
        reads+=1;v=cycle()
        if reads>1:v['attempts_started']=2
        return v
    with pytest.raises(Exception,match='SUPERVISOR_CHANGED'):
        cohort.capture(context,observe=lambda *_:identity(),read_cycle=read,process=Handle)
    assert len(made)==3 and all(h.closed for h in made)

@pytest.mark.parametrize('role',['parent','launcher','child'])
def test_cleanup_requires_every_physical_exit(role,monkeypatch):
    monkeypatch.setattr(cohort,'require_tags',lambda *_:None)
    proof={'exit_confirmed':True,'retained_handle':True,'force_used':False,'cohort':cycle(),
        'processes':{r:{'pid':cycle()[r]['pid'],'birth_filetime':cycle()[r]['birth'],
            'physical_exit_confirmed':True,'terminate_right':False} for r in cohort.ROLES}}
    cohort.validate_exit(None,proof)
    proof['processes'][role]['physical_exit_confirmed']=False
    with pytest.raises(Exception,match='ALL_COHORT_EXITS_REQUIRED'):cohort.validate_exit(None,proof)

def test_current_commands_preserve_cli45_and_only_new_python():
    amendment=json.loads((HERE/'amendment.json').read_bytes())
    proposal=json.loads(Path(amendment['original']['proposal']).read_bytes())
    original=json.loads(Path(proposal['execution_bundle']['commands']['path']).read_bytes())
    current=ctx.current_commands(original,'newpython')
    assert len(current['steps'])==4 and current['counts']['implicit_starts']==0
    for step in current['steps']:
        assert step['argv'][:3]==['newpython','-X','utf8']
        assert step['argv'][step['argv'].index('--timeout')+1]=='45'
        assert '--force' not in step['argv']
    assert 'guards' not in current and 'authorization_received' not in current

def test_package_gate_rejects_wrong_prefix_before_payload_reads():
    amendment=json.loads((HERE/'amendment.json').read_bytes())
    with pytest.raises(Exception,match='INSTALLED_PREFIX_MISMATCH'):
        ctx.verify_package(amendment,prefix='C:/not-the-installed-prefix')

def test_gate_composed_sources_and_new_prefix():
    args=SimpleNamespace(amendment=str(HERE/'amendment.json'),expected_amendment_sha256=ctx.sha(HERE/'amendment.json'))
    value=ctx.gate(args)
    assert value.P['package_pins']['payload_count']==1002
    assert value.P['controller_preparation']['policy']['carry_in_tokens']==272648
    assert value.P['controller_preparation']['policy']['carry_in_admissions']==11
    assert value.P['request_ids']['work']==['m1v14-local-work-12','m1v14-local-work-13']
    assert not value.PUBLIC.exists() and not value.PRIVATE.exists()
    assert value.stop_argv('nexus')[:3]==[value.installed['python'],'-X','utf8']

def test_entry_refuses_remote_before_run(tmp_path):
    import request_entry
    (tmp_path/'root-driver-preparation.json').write_text('{}')
    context=SimpleNamespace(PUBLIC=tmp_path,amendment={})
    with pytest.raises(Exception,match='LOCAL_RESUME_ONLY'):
        request_entry.execute(context,'work',['connector','useful'],run=lambda *_:pytest.fail('executed'))

def test_passive_readiness_never_masks_positive_error(tmp_path):
    value={'component':'nexus','action':'start','returncode':0}
    (tmp_path/'lifecycle-nexus-start-result.json').write_text(json.dumps(value))
    def fail(_):raise ValueError('SERVICE_CONTEXT_CHANGED')
    with pytest.raises(ValueError,match='SERVICE_CONTEXT_CHANGED'):
        cohort.await_ready(SimpleNamespace(PUBLIC=tmp_path),observe=fail,clock=lambda:0,sleep=lambda _:None)

def test_late_ready_cannot_extend_passive_deadline(tmp_path):
    (tmp_path/'lifecycle-nexus-start-result.json').write_text(json.dumps({'component':'nexus','action':'start','returncode':0}))
    clock=iter([0,0,181])
    with pytest.raises(Exception,match='PASSIVE_READINESS_DEADLINE'):
        cohort.await_ready(SimpleNamespace(PUBLIC=tmp_path),observe=lambda _:identity(),clock=lambda:next(clock),sleep=lambda _:None)

def test_source_process_has_query_sync_only():
    text=(HERE/'cohort.py').read_text(encoding='utf-8')
    assert 'k.OpenProcess(0x1000 | 0x100000, False, pid)' in text
    assert 'TerminateProcess' not in text and 'can_terminate=True' not in text
