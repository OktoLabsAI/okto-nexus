"""Pure disposable fixtures: no native task, process launch, network or termination."""
import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import json
import pytest
import run as campaign
import runtime_support as support

@pytest.fixture(autouse=True)
def no_effects(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('REAL_EFFECT_FORBIDDEN')
    monkeypatch.setattr(support.subprocess,'Popen',forbidden)
    monkeypatch.setattr(support.socket,'socket',forbidden)
    monkeypatch.setattr(support.ctypes,'WinDLL',forbidden)
    monkeypatch.setattr(campaign,'native_stamp',forbidden)

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    root=tmp_path/'synthetic';root.mkdir()
    for module in (campaign,support):
        monkeypatch.setattr(module,'ROOT',root)
        monkeypatch.setattr(module,'PUBLIC',root/'public')
        monkeypatch.setattr(module,'PRIVATE',root/'private')
    for name in ('public','private','nexus','connector'): (root/name).mkdir()
    monkeypatch.setattr(support,'HANDLES',[]);monkeypatch.setattr(support,'CHILDREN',[])
    image=root/'pythonw.exe';image.write_bytes(b'NOT AN EXECUTABLE')
    plan={'root':str(root),'python':'fixture-python','python_images':{str(image):campaign.sha(image)},
        'instance_ids':{'nexus':'fixture-nexus','connector':'fixture-connector'},
        'tasks':{'nexus':'fixture-task-nexus','connector':'fixture-task-connector'},
        'homes':{n:str(root/n) for n in ('nexus','connector')},'environments':{'A':{'FIXTURE':'1'}},
        'uninstall_removes':{'nexus':[],'connector':[]},'observation_timeout_seconds':10}
    return root,plan,image

def owner_fixture(plan,image,name='nexus',generation='g0',birth=123):
    owner=NS(identity={'pid':123,'generation':generation,'instance_id':plan['instance_ids'][name]},
        image=str(image),birth=birth,handle=object(),dead=False)
    owner.exited=lambda:owner.dead
    owner.close=lambda:None
    calls=[]
    class Terminate:
        def __call__(self,handle,code):
            calls.append((handle,code));owner.dead=True;return True
    owner.kernel=NS(TerminateProcess=Terminate())
    ready={**owner.identity,'state':'ready','supervisor':'windows-task-scheduler','ready_for_queries':True,'running':True,'ipc_ok':True}
    task=NS(active=True,digest='digest',enabled=True,state=4,last_result=0)
    contract={'name':plan['tasks'][name],'digest':'digest'}
    return owner,ready,task,contract,calls

@pytest.mark.parametrize('change',['generation','pid','instance','state','supervisor','task_digest','task_name','inactive','image','birth','exited'])
def test_crash_refuses_any_owner_disagreement(fixture,change):
    root,plan,image=fixture;owner,ready,task,contract,calls=owner_fixture(plan,image)
    if change in ('generation','pid','instance'):ready[{'instance':'instance_id'}.get(change,change)]='foreign'
    if change=='state':ready['state']='starting'
    if change=='supervisor':ready['supervisor']='foreground'
    if change=='task_digest':task.digest='foreign'
    if change=='task_name':contract['name']='foreign'
    if change=='inactive':task.active=False
    if change=='image':image.write_bytes(b'CHANGED')
    if change=='birth':owner.birth=0
    if change=='exited':owner.dead=True
    with pytest.raises(ValueError):campaign.validate_crash_selection(plan,'nexus',owner,ready,task,contract)
    assert calls==[]

def test_crash_uses_reserved_retained_handle_once(fixture,monkeypatch):
    root,plan,image=fixture;owner,ready,task,contract,calls=owner_fixture(plan,image)
    monkeypatch.setattr(campaign,'inspect',lambda *a:ready)
    service=NS(observe=lambda:({},task))
    campaign.crash_once(plan,'nexus',owner,service,contract,0)
    assert calls==[(owner.handle,3)] and owner.exited()
    proof=json.loads((root/'public/nexus-crash-0.json').read_bytes())
    assert proof['exit_confirmed'] and proof['retained_handle'] and not proof['canonical_force_stop_used']
    owner.dead=False
    with pytest.raises(FileExistsError):campaign.crash_once(plan,'nexus',owner,service,contract,0)
    assert len(calls)==1

def test_drift_after_reservation_never_terminates(fixture,monkeypatch):
    root,plan,image=fixture;owner,ready,task,contract,calls=owner_fixture(plan,image)
    observations=iter([ready,{**ready,'generation':'changed'}])
    monkeypatch.setattr(campaign,'inspect',lambda *a:next(observations))
    with pytest.raises(ValueError,match='READY_OWNER_CHANGED'):
        campaign.crash_once(plan,'nexus',owner,NS(observe=lambda:({},task)),contract,0)
    assert calls==[] and (root/'private/nexus-crash-0.reserved.json').is_file()

@pytest.mark.parametrize('number',[-1,4,True])
def test_no_fifth_or_invalid_crash(fixture,number):
    _,plan,image=fixture;owner,ready,task,contract,calls=owner_fixture(plan,image)
    with pytest.raises(ValueError,match='CRASH_LIMIT'):
        campaign.crash_once(plan,'nexus',owner,NS(observe=lambda:({},task)),contract,number)
    assert not calls

def test_native_retry_contract_exact(fixture,monkeypatch):
    _,plan,_=fixture;monkeypatch.setattr(campaign,'native_stamp',lambda _: 'stamp')
    def task(interval,count,policy):
        xml=f'<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Settings><RestartOnFailure><Interval>{interval}</Interval><Count>{count}</Count></RestartOnFailure><MultipleInstancesPolicy>{policy}</MultipleInstancesPolicy></Settings></Task>'
        return NS(active=True,enabled=True,digest='d',xml=xml)
    for interval,count,policy in [('PT1M','3','IgnoreNew'),('PT30S','3','IgnoreNew'),('PT1M','4','IgnoreNew'),('PT1M','3','Parallel')]:
        service=NS(name=plan['tasks']['nexus'],observe=lambda:({'owned':True},task(interval,count,policy)))
        if (interval,count,policy)==('PT1M','3','IgnoreNew'):
            assert campaign.native_contract(service)['count']==3
        else:
            with pytest.raises(ValueError,match='RETRY_CONTRACT_CHANGED'):campaign.native_contract(service)

def test_start_exit3_retained_while_late_ready_is_observed(fixture,monkeypatch):
    root,plan,image=fixture
    plan['commands']={'nexus':{'start':{'argv':['fixture-python','-I','-B','-X','utf8','start'],'cwd':str(root),'environment':'A'}}}
    class Child:
        pid=44
        def wait(self):return 3
        def poll(self):return 3
    def popen(argv,**kw):
        kw['stdout'].write(json.dumps({'state':'starting','reason':'SUPERVISOR_PENDING','label':'ação'},ensure_ascii=False).encode('utf-8'));return Child()
    monkeypatch.setattr(support.subprocess,'Popen',popen)
    code,value=support.cli(plan,'nexus','start');assert code==3 and value['label']=='ação'
    _,ready,_,_,_=owner_fixture(plan,image)
    statuses=iter([{'state':'starting'},ready]);monkeypatch.setattr(support,'inspect',lambda *a:next(statuses))
    monkeypatch.setattr(support.time,'sleep',lambda _:None)
    assert support.wait_ready(plan,'nexus','windows-task-scheduler')==ready
    saved=json.loads((root/'public/nexus-start.json').read_bytes())
    assert saved['returncode']==3 and saved['result']['reason']=='SUPERVISOR_PENDING'

@pytest.mark.parametrize('change',['none','launch','active','owner'])
def test_quiet_observation_refuses_extra_native_attempt(fixture,monkeypatch,change):
    root,plan,_=fixture;clock=[0]
    monkeypatch.setattr(campaign.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(campaign.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    monkeypatch.setattr(campaign,'native_stamp',lambda _: 'new' if change=='launch' and clock[0]>=1 else 'old')
    task=NS(state=3,active=False)
    def current(*a):
        if change=='active' and clock[0]>=1:task.active=True
        return {'state':'unknown','reason':'SUPERVISOR_LAST_ATTEMPT_FAILED','pid':999 if change=='owner' and clock[0]>=1 else None}
    monkeypatch.setattr(campaign,'inspect',current)
    service=NS(name='owned',tasks=NS(read=lambda _:task))
    if change=='none':
        proof=campaign.quiet(plan,'nexus',service,3,'quiet','SUPERVISOR_LAST_ATTEMPT_FAILED')
        assert proof['samples']==4 and proof['seconds']==3
    else:
        with pytest.raises(ValueError):campaign.quiet(plan,'nexus',service,3,'quiet','SUPERVISOR_LAST_ATTEMPT_FAILED')
        assert not (root/'public/nexus-quiet.json').exists()

@pytest.mark.parametrize('code,outcome',[(0,'drained'),(3,'drained'),(0,'unconfirmed')])
def test_normal_stop_requires_success_and_physical_exit(fixture,monkeypatch,code,outcome):
    root,plan,image=fixture;owner,_,_,_,calls=owner_fixture(plan,image);owner.dead=True
    monkeypatch.setattr(support,'cli',lambda *a:(code,{'shutdown_outcome':outcome}))
    monkeypatch.setattr(support,'inspect',lambda *a:{'state':'stopped'})
    service=NS(name='owned',tasks=NS(read=lambda _:NS(active=False,state=3)))
    if code==0 and outcome=='drained':
        support.stop_owner(plan,'nexus','stop',owner,service,task_present=True)
        assert json.loads((root/'public/nexus-stop-physical-exit.json').read_bytes())['physical_exit_confirmed']
    else:
        with pytest.raises(ValueError,match='NORMAL_STOP_NOT_DRAINED'):support.stop_owner(plan,'nexus','stop',owner,service,task_present=True)
    assert not calls

def test_normal_stop_unconfirmed_physical_exit_never_publishes_proof(fixture,monkeypatch):
    root,plan,image=fixture;owner,_,_,_,calls=owner_fixture(plan,image);clock=[0]
    monkeypatch.setattr(support,'cli',lambda *a:(0,{'shutdown_outcome':'drained'}))
    monkeypatch.setattr(support.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(support.time,'sleep',lambda _:clock.__setitem__(0,clock[0]+1))
    service=NS(name='owned',tasks=NS(read=lambda _:NS(active=False,state=3)))
    with pytest.raises(ValueError,match='PHYSICAL_EXIT_UNCONFIRMED'):
        support.stop_owner(plan,'nexus','stop',owner,service,task_present=True)
    assert not calls and not (root/'public/nexus-stop-physical-exit.json').exists()

def test_native_failure_consumes_selection_without_replay(fixture,monkeypatch):
    root,plan,image=fixture;owner,ready,task,contract,calls=owner_fixture(plan,image)
    monkeypatch.setattr(campaign,'inspect',lambda *a:ready)
    class FailedTerminate:
        def __call__(self,handle,code):calls.append((handle,code));return False
    owner.kernel.TerminateProcess=FailedTerminate();service=NS(observe=lambda:({},task))
    with pytest.raises(ValueError,match='FAULT_INJECTION_UNCONFIRMED'):
        campaign.crash_once(plan,'nexus',owner,service,contract,0)
    with pytest.raises(FileExistsError):campaign.crash_once(plan,'nexus',owner,service,contract,0)
    assert len(calls)==1 and not (root/'public/nexus-crash-0.json').exists()

@pytest.mark.parametrize('eventual_inactive',[True,False])
def test_stop_waits_bounded_for_scheduler_after_physical_exit(fixture,monkeypatch,eventual_inactive):
    root,plan,image=fixture;owner,_,_,_,calls=owner_fixture(plan,image);owner.dead=True
    clock=[0];reads=[]
    monkeypatch.setattr(support,'cli',lambda *a:(0,{'shutdown_outcome':'drained'}))
    monkeypatch.setattr(support,'inspect',lambda *a:{'state':'stopped'})
    monkeypatch.setattr(support.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(support.time,'sleep',lambda _:clock.__setitem__(0,clock[0]+1))
    def read(name):
        reads.append(name)
        return NS(active=not(eventual_inactive and len(reads)>=3),state=3 if eventual_inactive and len(reads)>=3 else 4)
    service=NS(name='exact-owned-task',tasks=NS(read=read))
    if eventual_inactive:
        support.stop_owner(plan,'nexus','stop',owner,service,task_present=True)
        proof=json.loads((root/'public/nexus-stop-physical-exit.json').read_bytes())
        assert proof['physical_exit_confirmed'] and not proof['force_used'] and clock[0]==2
    else:
        with pytest.raises(ValueError,match='NATIVE_TASK_EXIT_UNCONFIRMED'):
            support.stop_owner(plan,'nexus','stop',owner,service,task_present=True)
        assert clock[0]==30 and not (root/'public/nexus-stop-physical-exit.json').exists()
    assert set(reads)=={'exact-owned-task'} and calls==[]

@pytest.mark.parametrize('early_backoff',[False,True])
def test_finite_flow_has_eight_crashes_six_restarts_and_no_manual_retry(fixture,monkeypatch,early_backoff):
    root,plan,image=fixture
    for name in ('project-a','caller-b','profile'): (root/name).mkdir()
    (root/'plan.json').write_text('{}')
    monkeypatch.setattr(campaign,'package_proof',lambda _:None)
    monkeypatch.setattr(support,'secure',lambda p:p.mkdir(exist_ok=True))
    monkeypatch.setattr(support,'port_available',lambda _:None)
    monkeypatch.setattr(campaign.os,'environ',{})
    trace=[];crashes=[];owners={};counts={'nexus':0,'connector':0};tasks={n:None for n in counts}
    def service(name):
        return NS(name=plan['tasks'][name],tasks=NS(read=lambda _:tasks[name]),
            control=lambda _: {'desired':'draining'},receipt=lambda:{'owned':True})
    services={name:service(name) for name in counts}
    import okto_nexus.adapters.outbound.service_manager.installation as ni
    import okto_nexus_connector.platform.user_service as ci
    monkeypatch.setattr(ni,'ServerInstallation',lambda *a:services['nexus'])
    monkeypatch.setattr(ci,'UserService',lambda *a:services['connector'])
    def cli(_plan,name,phase):
        trace.append((name,phase))
        if phase=='install':tasks[name]=NS(state=3,active=False,last_result=3)
        if phase=='uninstall':tasks[name]=None
        return (3 if phase in ('start-initial','next-connect') else 0),{'shutdown_outcome':'drained'}
    monkeypatch.setattr(campaign,'cli',cli)
    def ready(_plan,name,supervisor):
        count=counts[name];counts[name]+=1
        seconds=1000+count*(1 if early_backoff and count>=2 else 61)
        owner,value,*_=owner_fixture(plan,image,name,generation='g'+str(count),birth=int((11644473600+seconds)*10_000_000))
        owners[name]=owner;support.HANDLES.append(owner);return owner,value
    monkeypatch.setattr(campaign,'own_ready',ready)
    monkeypatch.setattr(campaign,'stop_owner',lambda _p,n,*a,**k:setattr(owners[n],'dead',True))
    def current(_plan,name):
        return {'state':'stopped','pid':None,'reason':'SUPERVISOR_LAST_ATTEMPT_FAILED','next_action':'inspect'}
    monkeypatch.setattr(campaign,'inspect',current)
    monkeypatch.setattr(campaign,'native_contract',lambda s:{'name':s.name,'digest':'d','last_run_time':'initial'})
    monkeypatch.setattr(campaign,'native_stamp',lambda s: str(counts['nexus' if s is services['nexus'] else 'connector']))
    monkeypatch.setattr(campaign,'quiet',lambda *a:trace.append((a[1],a[4])))
    monkeypatch.setattr(campaign,'wait_native_inactive',lambda s:NS(last_result=3))
    def crash(_plan,name,owner,_service,_contract,number):
        crashes.append((name,number));owner.dead=True
        return owner.birth/10_000_000-11644473600
    monkeypatch.setattr(campaign,'crash_once',crash)
    monkeypatch.setattr(support,'fingerprint',lambda *a:{'fixture-db':{'sha256':'safe'}})
    if early_backoff:
        with pytest.raises(ValueError,match='BACKOFF_SHORTER'):campaign.execute(plan)
        assert crashes==[('nexus',0)] and ('nexus','uninstall') not in trace
    else:
        campaign.execute(plan)
        assert crashes==[(name,n) for name in ('nexus','connector') for n in range(4)]
        assert counts=={'nexus':5,'connector':5}
        assert [p for _,p in trace if p.startswith('start')]==['start-initial','start-initial','start-for-crash']
        assert all(o.exited() for o in support.HANDLES)
        assert json.loads((root/'public/qualification.json').read_bytes())['canonical_force_stop_used'] is False
