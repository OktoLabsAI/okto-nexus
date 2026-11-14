"""Continue an exactly pinned pre-controller, read-only adoption refusal once."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def require(ok,code):
    if not ok:raise RuntimeError(code)
def load(name,pin):
    require(sha(pin['path'])==pin['sha256'],'PIN_CHANGED')
    spec=importlib.util.spec_from_file_location(name,pin['path']);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m

def validate_before(context,m):
    for pin in m['before'].values():require(sha(pin['path'])==pin['sha256'],'FAILED_ATTEMPT_CHANGED')
    returned=read(m['before']['returned']['path']);stdout=read(m['before']['stdout']['path'])
    require(returned['returncode']==2 and returned['wrapper_exit_confirmed'] is True
        and returned['stdout_sha256']==m['before']['stdout']['sha256']
        and returned['stderr_sha256']==m['before']['stderr']['sha256']
        and stdout=={'status':'REFUSED_OR_UNCONFIRMED','code':'NEXUS_OWNER_NOT_READY'},'BEFORE_EFFECT_REFUSAL_REQUIRED')
    for path in (context.PRIVATE/'controller.json',context.PRIVATE/'predecessor-work-checkpoint.json',context.PUBLIC/'adopt-local-result.json'):
        require(not path.exists(),'ADOPTION_ALREADY_ADVANCED')

def preserve_reservation(common,context,name,value,pin):
    if name!='adopt-local-reserved.json':return common.public_save(context,name,value)
    require(value=={'state':'READ_ONLY_ADOPTION_RESERVED','model_admissions':0},'RESERVATION_SEMANTICS_CHANGED')
    require(sha(pin['path'])==pin['sha256'],'OLD_RESERVATION_CHANGED')
    old=read(pin['path']);common.require_tags(old,context)
    require(all(old.get(k)==v for k,v in value.items()),'OLD_RESERVATION_INVALID')
    return Path(pin['path'])

def bounded_status(context,component,observer,selected):
    require(component=='nexus','ONLY_OWN_NEXUS')
    from okto_nexus.adapters.outbound.service_manager import inspection
    original=inspection.inspect_local_server
    def ten_seconds(**kwargs):
        require(kwargs.get('timeout')==5 and Path(kwargs['home']).resolve()==Path(context.P['paths']['server_home']).resolve()
            and kwargs.get('host')=='127.0.0.1' and kwargs.get('port')==58631,'STATUS_SELECTION_CHANGED')
        kwargs['timeout']=10
        return original(**kwargs)
    inspection.inspect_local_server=ten_seconds
    try:value=observer.status(context,component)
    finally:inspection.inspect_local_server=original
    observer.same_owner(selected,value)
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('preflight','execute'));p.add_argument('--manifest-sha256',required=True)
    args=p.parse_args();require(sha(HERE/'manifest.json')==args.manifest_sha256,'MANIFEST_CHANGED')
    m=read(HERE/'manifest.json');require(sha(__file__)==m['helper_sha256'],'HELPER_CHANGED')
    common=load('driver_common',m['sources']['common'])
    context=common.gate(SimpleNamespace(**m['authority']))
    validate_before(context,m)
    observer=load('m1_v14_observation',m['sources']['observer'])
    adopt=load('adopt_local',m['sources']['adopt'])
    selected=read(m['before']['owner']['path']);common.require_tags(selected,context)
    require(selected['pid']==5132 and selected['birth_filetime']==134391500501368514
        and selected['generation']=='c9f085a3b8f3f61558fb5ad9cc302ee2','SELECTED_OWNER_CHANGED')
    if args.mode=='preflight':
        print(json.dumps({'state':'OFFLINE_PREFLIGHT_PASS','controller_snapshot_result_absent':True,'original_refusal_preserved':True}));return 0
    runtime=HERE/'runtime';runtime.mkdir(exist_ok=True)
    common.reserve(runtime/'continuation-reserved.json',{**common.tags(context),'manifest_sha256':args.manifest_sha256,
        'source_attempt_returncode':2,'source_attempt_preserved':True,'maximum_new_adoptions':1,
        'http_methods':['GET'],'status_timeout_seconds':10,'model_admissions':0,'reserved_at':time.time()})
    handle=observer.PhysicalProcess(selected['pid'])
    try:
        require(handle.birth()==selected['birth_filetime'] and not handle.wait(0),'OWNER_EXITED_OR_REUSED')
        old_save=adopt.public_save
        adopt.public_save=lambda ctx,name,value:preserve_reservation(common,ctx,name,value,m['before']['reservation'])
        try:
            result=adopt.adopt(context,observe=lambda ctx,component:bounded_status(ctx,component,observer,selected))
        finally:adopt.public_save=old_save
        require(sha(m['before']['reservation']['path'])==m['before']['reservation']['sha256'],'ORIGINAL_RESERVATION_CHANGED')
        receipt={**common.tags(context),'status':'ADOPTION_CONTINUATION_COMPLETED','manifest_sha256':args.manifest_sha256,
            'original_returncode':2,'original_result_unchanged':True,'model_admissions':0,'setup_replayed':False,
            'adoption_result_sha256':sha(context.PUBLIC/'adopt-local-result.json'),
            'new_controller_sha256':sha(context.PRIVATE/'controller.json'),
            'snapshot_sha256':sha(context.PRIVATE/'predecessor-work-checkpoint.json'),
            'finished_at':time.time(),'process_exit_confirmation':'root must observe this helper exit; function return is not process-exit proof'}
        common.reserve(runtime/'continuation-result.json',receipt)
        common.public_save(context,'adopt-local-continuation.json',receipt)
        print(json.dumps(receipt));return 0
    except BaseException as error:
        common.reserve(runtime/'continuation-unconfirmed.json',{**common.tags(context),'error_type':type(error).__name__,
            'code':getattr(error,'code',None),'controller_exists':(context.PRIVATE/'controller.json').exists(),
            'snapshot_exists':(context.PRIVATE/'predecessor-work-checkpoint.json').exists(),
            'original_adoption_result_exists':(context.PUBLIC/'adopt-local-result.json').exists()})
        raise
    finally:handle.close()

if __name__=='__main__':raise SystemExit(main())
