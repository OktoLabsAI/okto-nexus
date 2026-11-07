from pathlib import Path
import json,sys,time
sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')
from m1_real_lifecycle import P,C,ROOT,REPO
sys.path.insert(0,str(REPO/'plans/agent_ops/evidence/r3-m1-controller/preparation'))
from controller import Controller
from okto_nexus.adapters.inbound.cli.work import open_work
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
service=resolve_local_service(C['service_selection_args'])
flow=open_work(service,'m1-local')
original=flow.call
def readonly(method,path,body=None):
    assert method=='GET','Observation must not replay any effect'
    return original(method,path,body)
flow.call=readonly
controller=Controller(ROOT/'private/controller.json',ROOT)
controller.attach('local',flow)
def no_new_stop():raise AssertionError('Existing interruption must be observed, not repeated')
controller.attach_owner('local',P['paths']['server_home'],no_new_stop)
try:
    until=time.monotonic()+60
    while True:
        summary=controller.poll()
        r=controller.data['requests']['m1-local-work-01']
        binding=flow.binding()
        control=flow.operation(flow.document['control']['submission']['operation_id'],binding)
        work=flow.operation(r['operation'],binding)
        if (r['settled'] and control.get('executor_stage') in ('SUCCEEDED','FAILED','CANCELLED')) or time.monotonic()>=until:break
        time.sleep(.2)
    result={'read_only':True,'summary':summary,'work':{k:work.get(k) for k in ('operation_id','executor_stage','admission_state','possible_effect','error')},
            'control':{k:control.get(k) for k in ('operation_id','executor_stage','admission_state','possible_effect','error')},
            'request_settled':r['settled'],'stop_selected':r['stop_selected'],
            'report_exists':(Path(P['paths']['local_deliverables'])/'report.json').exists(),
            'new_productive_dispatches':0,'repeated_controls':0}
    (ROOT/'public/interruption-observed.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
finally:controller.close()
