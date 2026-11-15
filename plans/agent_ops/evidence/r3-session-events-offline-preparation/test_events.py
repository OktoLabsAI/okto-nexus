import copy,json
from unittest.mock import Mock
import pytest
import event_native as N
import event_observer as O
import event_lifecycle as L

def component(name='nexus',generation='old',birth=133485408000000000):
    return {'component':name,'cohort_confirmed':True,'canonical':{'state':'ready','ready_for_queries':True,'storage_initialized':True,'generation':generation},
        'task':{'present':True,'enabled':True,'logon_trigger_enabled':True,'restart_on_failure_present':False,'digest':'d','last_run_time_utc':'2024-01-01T00:00:05+00:00'},
        'cohort':{'cycle_id':'c','child_acknowledged':True,**{r:{'pid':i+1,'birth':birth} for i,r in enumerate(N.ROLES)}},
        'receipts':{'shutdown':{'present':False}}}
def pair(event='02-sign-out-logon'):
    b={'event_id':event,'utc':'2024-01-01T00:00:00+00:00','own_session':{'principal_sha256':'p','logon_authentication_id':'a','last_boot_up_time_dmtf':'b0'},
       'components':{n:component(n) for n in O.NAMES},'invocation_inventory':{'start':'hash'}}
    c=copy.deepcopy(b);c['utc']='2024-01-01T00:00:06+00:00';c['own_session'].update(logon_authentication_id='b',logon_time_utc='2024-01-01T00:00:02+00:00')
    for value in c['components'].values():
        value['canonical']['generation']='new';value['cohort']['cycle_id']='new'
        for r in N.ROLES:value['cohort'][r]['birth']=133485408040000000
    a={'event_id':event,'before_sha256':'bhash','current':c,'invocation_inventory':dict(b['invocation_inventory']),
       'actual_event':{'event_id':event,'action':O.ACTIONS[event],'performed_by_user':True,'no_manual_start_or_connect':True,
       'source_reference':'synthetic fixture only','started_utc':'2024-01-01T00:00:01+00:00','completed_utc':'2024-01-01T00:00:04+00:00'}}
    return b,a

@pytest.mark.parametrize('receipt',[{'present':False},{'present':True,'unconfirmed':True},
    {'present':True,'fields':{'state':'DRAINED','generation':'new'}},{'present':True,'fields':{'state':'DRAINED'}}])
def test_missing_malformed_or_other_generation_never_drained(receipt):
    b,a=pair();a['current']['components']['nexus']['receipts']['shutdown']=receipt
    value=O.assess(b,a,'bhash')
    assert value['components']['nexus']['old_generation_shutdown_receipt']['state']=='UNKNOWN'
    assert value['prior_generation_physical_exit']=='UNKNOWN' and not value['productive_continuity_claimed']

def test_exact_old_receipt_is_separate_from_physical_exit():
    b,a=pair();a['current']['components']['nexus']['receipts']['shutdown']={'present':True,'sha256':'r','fields':{'state':'DRAINED','generation':'old'}}
    value=O.assess(b,a,'bhash');assert value['components']['nexus']['old_generation_shutdown_receipt']['state']=='DRAINED'
    assert value['components']['nexus']['owner_relation']=='REPLACED' and value['prior_generation_physical_exit']=='UNKNOWN'

def test_partial_retained_proof_never_all_exit():
    b,a=pair();proof={'before_sha256':'bhash','identities':O.expected_handles(b),'proof_source':'SAME_RETAINED_HANDLES',
        'all_physical_exit_confirmed':True,'processes':{'nexus/parent':{'physical_exit_confirmed':True,'exit_code':0}}}
    assert O.assess(b,a,'bhash',proof)['prior_generation_physical_exit']=='UNKNOWN'

def test_retained_identity_mismatch_refuses():
    b,a=pair()
    with pytest.raises(RuntimeError,match='IDENTITY'):O.assess(b,a,'bhash',{'before_sha256':'wrong','identities':{}})

def test_same_pid_different_birth_replaced():
    b,a=pair();a['current']['components']['nexus']['canonical']['generation']='old'
    assert O.assess(b,a,'bhash')['components']['nexus']['owner_relation']=='REPLACED'

def test_hash_event_and_action_boundaries():
    b,a=pair()
    with pytest.raises(RuntimeError,match='HASH'):O.assess(b,a,'wrong')
    a['actual_event']['action']='restart-sign-in'
    with pytest.raises(RuntimeError,match='MARKER'):O.assess(b,a,'bhash')

def test_logon_correlation_requires_task_and_no_intervening_start():
    b,a=pair();value=O.assess(b,a,'bhash')
    assert value['components']['nexus']['logon_trigger_correlated'] and not value['boot_without_login_claimed']
    a['current']['components']['nexus']['task']['digest']='edited'
    assert not O.assess(b,a,'bhash')['components']['nexus']['logon_trigger_correlated']
    a['current']['components']['nexus']['task']['digest']='d';a['invocation_inventory']['extra-start']='x'
    assert not O.assess(b,a,'bhash')['components']['nexus']['logon_trigger_correlated']

@pytest.mark.parametrize('event',O.EVENTS)
def test_events_are_distinct_and_never_assert_work_settlement(event):
    b,a=pair(event);r=O.assess(b,a,'bhash')
    assert r['event_id']==event and r['components']['nexus']['work_settlement']=='NOT_ASSERTED'
    if event!='02-sign-out-logon':assert not r['components']['nexus']['logon_trigger_correlated']

def test_write_once_and_fsync(tmp_path,monkeypatch):
    sync=Mock();monkeypatch.setattr(O.os,'fsync',sync);p=tmp_path/'record.json';O.save(p,{'x':1});sync.assert_called_once()
    with pytest.raises(FileExistsError):O.save(p,{'x':2})
    assert O.read(p)=={'x':1}

@pytest.mark.parametrize('token',['filetime:0','filetime:001','filetime:-1','filetime:١','other:123'])
def test_connector_birth_token_invalid(token):
    cycle={r:{'pid':1,'birth_token':token} for r in N.ROLES}
    with pytest.raises(RuntimeError):N.normalize_cycle(cycle,'connector')

def test_connector_birth_projection_is_exact():
    c={r:{'pid':i+1,'birth_token':'filetime:123456789012345678'} for i,r in enumerate(N.ROLES)}
    assert N.normalize_cycle(c,'connector')['child']=={'pid':3,'birth':123456789012345678}

class Handle:
    def __init__(self,pid):self.pid=pid;self.birth=7;self.image='python';self.closed=False
    def exited(self):return False
    def close(self):self.closed=True

def test_capture_birth_mismatch_closes_without_claim(monkeypatch):
    task=Mock(digest='d');service=Mock(name='n');service.tasks.read.return_value=task
    monkeypatch.setattr(N,'installation',lambda *a:service);monkeypatch.setattr(N,'task_projection',lambda *a:{})
    monkeypatch.setattr(N,'exact_task_last_run',lambda *a:None);monkeypatch.setattr(N,'canonical_status',lambda *a:{'instance_id':'i','pid':3,'generation':'g'})
    monkeypatch.setattr(N,'receipt_projection',lambda *a:{})
    monkeypatch.setattr(N,'read_cycle',lambda *a:{r:{'pid':i+1,'birth':8} for i,r in enumerate(N.ROLES)})
    handles=[]
    def factory(pid):h=Handle(pid);handles.append(h);return h
    result,retained=N.collect_component({'instance_ids':{'nexus':'i'},'python_images':{'python':'h'}},'nexus',retain=True,process=factory)
    assert not result['cohort_confirmed'] and retained=={} and handles[0].closed

def test_after_deadline_has_no_launch_and_keeps_unknown(tmp_path,monkeypatch):
    b,a=pair();directory=tmp_path/'evidence'/b['event_id'];directory.mkdir(parents=True)
    (tmp_path/'plan.json').write_text('{}');b['plan_sha256']=O.digest(tmp_path/'plan.json');O.save(directory/'before.json',b)
    b['components']['nexus']['cohort_confirmed']=False
    times=iter([0,180]);snap=Mock(return_value=(b,{}));sleep=Mock()
    r=O.after({'root':str(tmp_path)},b['event_id'],a['actual_event'],snapshot=snap,clock=lambda:next(times),sleep=sleep)
    assert len(r['samples'])==1 and not r['automatic_start_selected'];snap.assert_called_once();sleep.assert_not_called()

def test_single_lifecycle_reservation_before_effect(tmp_path):
    d=tmp_path/'lifecycle';d.mkdir();(d/'prepared.json').write_text('{}');(tmp_path/'plan.json').write_text('{}')
    P={'root':str(tmp_path),'python':'python','commands':{'nexus':{'install':{'argv':['python','-I'],'environment':'A','cwd':str(tmp_path)}}},'environments':{'A':{}}}
    calls=[]
    def spawn(*args,**kwargs):
        assert (d/'nexus-install.reserved.json').exists();calls.append(args);return Mock(wait=Mock(return_value=0))
    assert L.invoke(P,'nexus','install',popen=spawn)['exit_code']==0
    with pytest.raises(FileExistsError):L.invoke(P,'nexus','install',popen=spawn)
    assert len(calls)==1

def test_uninstall_without_all_process_proofs_never_dispatches(tmp_path,monkeypatch):
    d=tmp_path/'lifecycle';d.mkdir();O.save(d/'nexus-cleanup-proof.json',{'component':'nexus','all_physical_exit_confirmed':False})
    effect=Mock();monkeypatch.setattr(L,'invoke',effect)
    with pytest.raises(RuntimeError,match='NOT_PROVED'):L.uninstall({'root':str(tmp_path)},'nexus')
    effect.assert_not_called()


def test_atomic_publish_keeps_incomplete_file_unreadable(tmp_path,monkeypatch):
    p=tmp_path/'after.json'
    def interrupted(*args):raise OSError('synthetic fsync interruption')
    monkeypatch.setattr(O.os,'fsync',interrupted)
    with pytest.raises(OSError):O.save(p,{'status':'partial'})
    assert not p.exists() and p.with_name('after.json.writing').exists()
    with pytest.raises(FileExistsError):O.save(p,{'status':'replay'})

def test_future_task_or_birth_is_not_logon_correlation():
    b,a=pair();v=a['current']['components']['nexus']
    v['task']['last_run_time_utc']='2099-01-01T00:00:05+00:00'
    assert not O.assess(b,a,'bhash')['components']['nexus']['logon_trigger_correlated']
    v['task']['last_run_time_utc']='2024-01-01T00:00:05+00:00'
    v['cohort']['parent']['birth']=200000000000000000
    assert not O.assess(b,a,'bhash')['components']['nexus']['logon_trigger_correlated']


def test_authorization_gate_real_loader_no_effect(tmp_path,monkeypatch):
    import event_entry as E
    monkeypatch.setattr(E,'HERE',tmp_path)
    runtime={'runtime':{}}
    O.save(tmp_path/'runtime-freeze.json',runtime)
    O.save(tmp_path/'package.json',{'files':[]})
    P={'root':str(tmp_path),'python':E.sys.executable,'python_prefix':E.sys.prefix,
       'package':{'path':str(tmp_path/'package.json'),'sha256':O.digest(tmp_path/'package.json')},
       'source_pins':[],'python_images':{},'events':[{'id':x} for x in O.EVENTS]}
    O.save(tmp_path/'plan.json',P)
    auth={'status':'USER_COORDINATED_EVENTS_SELECTED','plan_sha256':O.digest(tmp_path/'plan.json'),
          'runtime_freeze_sha256':O.digest(tmp_path/'runtime-freeze.json'),'manual_os_actions_only':True,
          'temporary_tasks_selected':True,'user_reference':'synthetic fixture, not authority','events':[O.EVENTS[0]]}
    O.save(tmp_path/'authorization.json',auth)
    loaded,selected=E.load(auth['runtime_freeze_sha256'],tmp_path/'authorization.json',O.digest(tmp_path/'authorization.json'))
    assert loaded==P and selected['events']==[O.EVENTS[0]]
    auth['status']='OFFLINE_DRAFT';(tmp_path/'authorization.json').write_text(json.dumps(auth))
    with pytest.raises(RuntimeError,match='NOT_SELECTED'):
        E.load(auth['runtime_freeze_sha256'],tmp_path/'authorization.json',O.digest(tmp_path/'authorization.json'))


def test_cleanup_phase_change_does_not_change_identity(tmp_path,monkeypatch):
    d=tmp_path/'lifecycle';d.mkdir();cohort={'cycle_id':'a','attempts_started':1,'child_acknowledged':True,'phase':'running',
        **{r:{'pid':i+1,'birth':7} for i,r in enumerate(N.ROLES)}}
    proof={'component':'nexus','all_physical_exit_confirmed':True,'native_inactive_same_definition':True,'force':False,
       'processes':{r:{'physical_exit_confirmed':True} for r in N.ROLES},'cohort':cohort,'task_digest':'t'}
    O.save(d/'nexus-cleanup-proof.json',proof);home=tmp_path/'home';home.mkdir()
    task=Mock(active=False,digest='t');service=Mock();service.observe.return_value=(None,task);service.tasks.read.return_value=None
    monkeypatch.setattr(N,'installation',lambda *a:service)
    monkeypatch.setattr(N,'read_cycle',lambda *a:{**cohort,'phase':'stopped'})
    effect=Mock(return_value={'exit_code':0});monkeypatch.setattr(L,'invoke',effect)
    result=L.uninstall({'root':str(tmp_path),'homes':{'nexus':str(home)}},'nexus')
    assert result['data_equal'] and result['task_absent'];effect.assert_called_once()
