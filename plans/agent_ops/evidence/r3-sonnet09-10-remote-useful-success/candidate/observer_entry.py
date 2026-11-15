"""Future explicit GET-only before/after observer using a pinned lifecycle plan."""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from fast_approval import require,read,exclusive
from dashboard_observer import observe

def main():
    p=argparse.ArgumentParser()
    for name in ('lifecycle-plan','lifecycle-sha256','selection-pins','scope','operation-id','stage','output'):
        p.add_argument('--'+name,required=True)
    a=p.parse_args();require(a.stage in ('before','after'),'STAGE_INVALID')
    path=Path(a.lifecycle_plan)
    require(hashlib.sha256(path.read_bytes()).hexdigest()==a.lifecycle_sha256,'LIFECYCLE_PIN_CHANGED')
    plan=read(path)
    for pin in plan['runtime_pins'].values():
        require(hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()==pin['sha256'],'LIFECYCLE_RUNTIME_CHANGED')
    sys.path.insert(0,str(path.parent))
    def load(name):
        pin=plan['runtime_pins'][name+'.py'];spec=importlib.util.spec_from_file_location(name,pin['path'])
        value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value
    context=load('recovery_context');N=load('recovery_observation');C=load('recovery_connector')
    X=context.RecoveryContext(path,a.lifecycle_sha256)
    selected={}
    for name,pin in read(a.selection_pins).items():
        require(name in ('nexus','connector'),'SELECTION_COMPONENT_CHANGED')
        require(hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()==pin['sha256'],'SELECTION_PIN_CHANGED')
        selected[name]=read(pin['path'])
    require(set(selected)=={'nexus','connector'},'TWO_SELECTIONS_REQUIRED')
    value=observe(X,N,C,expected_selections=selected,scope=read(a.scope),operation_id=a.operation_id,
                  operator_profile='m1-sonnet-human')
    value.update(stage=a.stage,lifecycle_plan_sha256=a.lifecycle_sha256)
    exclusive(a.output,value)
    print(json.dumps({'status':'INDEPENDENT_GET_OBSERVATION_RECORDED','stage':a.stage,
        'same_active_operation':value['same_active_operation'],'six_handles_live':value['six_handles_live']}))

if __name__=='__main__':main()
