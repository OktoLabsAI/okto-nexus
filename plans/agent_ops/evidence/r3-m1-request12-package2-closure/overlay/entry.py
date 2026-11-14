"""One transparent predispatch reentry; original gates, controller and outputs remain authoritative."""
from pathlib import Path
from types import SimpleNamespace
import argparse,hashlib,json,os,runpy,sys
HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12-package2')
sys.path.insert(0,str(BASE))
def require(value,code):
    if not value:raise ValueError(code)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def pincheck(pin):
    require(sha(pin['path'])==pin['sha256'],'REENTRY_SOURCE_CHANGED');return Path(pin['path'])
def parser():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--expected-manifest-sha256',required=True)
    p.add_argument('phase',choices=['useful','continuation']);return p

def static(args):
    require(Path(args.manifest).resolve()==HERE/'manifest.json' and sha(args.manifest)==args.expected_manifest_sha256,
        'REENTRY_MANIFEST_CHANGED')
    m=read(args.manifest)
    require(m['format']=='okto.m1.policy_import_overlay.v1' and m['maximum_useful_reentries']==1
        and m['new_model_ids']==['m1v14-local-work-12','m1v14-local-work-13'],'FINITE_REENTRY_REQUIRED')
    for entry in [*m['sources'].values(),*m['basis'].values()]:pincheck(entry)
    return m

def require_selection(context,m,phase):
    failed=read(m['basis']['failed_wrapper']['path']);context.common.require_tags(failed,context)
    require(failed['mode']=='work' and failed['selection']==['local','useful']
        and failed['returncode']==1 and failed['wrapper_exit_confirmed'] is True,
        'PREDISPATCH_FAILED_WRAPPER_REQUIRED')
    require(failed['stderr_sha256']==m['basis']['failed_stderr']['sha256'],'FAILURE_STDERR_CHANGED')
    trace=Path(m['basis']['failed_stderr']['path']).read_text(encoding='utf-8')
    require('assert POLICY == legacy_controller.POLICY' in trace and trace.rstrip().endswith('AssertionError'),
        'EXACT_POLICY_IMPORT_FAILURE_REQUIRED')
    cp=read(context.PRIVATE/'controller.json')
    if phase=='useful':
        require(sha(context.PRIVATE/'controller.json')==m['initial_checkpoint_sha256']
            and cp['requests']=={} and cp['collector']['state']['requests']=={} and cp['faults']==[],
            'NO_PRIOR_MODEL_RESERVATION_REQUIRED')
        require(not any(p.name.startswith('m1v14-local-work-12-') for p in context.PUBLIC.iterdir()),
            'PRIOR_DISPATCH_EVIDENCE_PRESENT')
    else:
        done=read(HERE/'runtime-private/work-local-useful.returned.json')
        require(done['returncode']==0 and done['wrapper_exit_confirmed'] is True,'REENTRY_USEFUL_WRAPPER_REQUIRED')
        result=read(context.PUBLIC/'m1v14-local-work-12-result.json')
        require(set(cp['requests'])=={'m1v14-local-work-12'} and cp['faults']==[], 'CONTINUATION_RESERVATION_CHANGED')
        record=cp['requests']['m1v14-local-work-12']
        require(result.get('useful_result_confirmed') is True and result['record']['settled'] is True
            and record['settled'] is True and record['canonical_stage']=='SUCCEEDED'
            and bool(record.get('session')) and result['record']['session']==record['session'],
            'SAME_SUCCESSFUL_SESSION_REQUIRED')

def load(args):
    m=static(args)
    from request_context import gate
    context=gate(SimpleNamespace(amendment=m['basis']['amendment']['path'],
        expected_amendment_sha256=m['basis']['amendment']['sha256']))
    require_selection(context,m,args.phase)
    sys.path.insert(0,str(context.modules))
    from legacy_controller import POLICY
    require(POLICY==context.amendment['policy'],'CURRENT_POLICY_REQUIRED')
    return context,m

def main():
    args=parser().parse_args();context,m=load(args)
    ledger=HERE/'runtime-private';reserved=read(ledger/('work-local-'+args.phase+'.reserved.json'))
    require(reserved.get('manifest_sha256')==args.expected_manifest_sha256 and reserved.get('phase')==args.phase,
        'INVOCATION_RESERVATION_REQUIRED')
    context.common.reserve(ledger/('work-local-'+args.phase+'.claimed.json'),
        {'phase':args.phase,'pid':os.getpid(),'manifest_sha256':args.expected_manifest_sha256})
    # The original Context, modules and checkpoint are unchanged. The only source
    # overlay imports the existing current POLICY, already matched above.
    context.remaining=['local',args.phase]
    path=pincheck(m['sources']['work_overlay'])
    sys.argv=[str(path),*context.common_args(),*context.remaining]
    runpy.run_path(str(path),run_name='__main__')
    return 0
if __name__=='__main__':raise SystemExit(main())
