from pathlib import Path
import json,sys,time
sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')
from m1_real_lifecycle import ROOT,REPO,P,C
sys.path.insert(0,str(REPO/'plans/agent_ops/evidence/r3-m1-controller/preparation'))
from controller import Controller
from response_loss import CampaignState,FiniteResponseLoss
from okto_nexus.adapters.inbound.cli.work import open_work
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock
service=resolve_local_service(C['service_selection_args'])
guard=ExclusiveFileLock(service.adapter.home/'terminal/profiles/m1-local.guard');guard.acquire()
controller=Controller(ROOT/'private/controller.json',ROOT)
flow=open_work(service,'m1-local');flow.call.timeout=.5
path=service.adapter.home/'terminal/work/m1-local.json'
driver=CampaignState(ROOT/'private/response-loss.json')
flow.call=FiniteResponseLoss(flow.call,lambda:json.loads(path.read_text()),driver,'local')
controller.attach('local',flow)
def no_new_stop():raise AssertionError('No repeated controller effect during close cleanup')
controller.attach_owner('local',P['paths']['server_home'],no_new_stop)
reservation=ROOT/'public/local-close-selected.json'
assert not reservation.exists()
session=controller.data['requests']['m1-local-work-01']['session']
with reservation.open('x') as f:json.dump({'action':'close','client_intent_id':'m1-local-close','session_id':session,'selected_at':time.time()},f)
try:
    operation=flow.submit(action='close',session_id=session,client_intent_id='m1-local-close')
    deadline=time.monotonic()+45
    while True:
        summary=controller.poll()
        current=flow.operation(operation['operation_id'],flow.binding())
        if current.get('executor_stage') in ('SUCCEEDED','FAILED','CANCELLED') or time.monotonic()>=deadline:break
        time.sleep(.2)
    runtime=flow.session(flow.binding(),session)
    result={'operation':{k:current.get(k) for k in ('operation_id','executor_stage','admission_state','possible_effect','error')},
            'session_id':session,'runtime_lifecycle_state':runtime.get('lifecycle_state'),'summary':summary,
            'productive_replay':False,'response_loss_driver':driver.snapshot()}
    (ROOT/'public/local-close-result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
finally:
    controller.close();guard.release()
