"""One canonical environment migration; no implicit start or runtime admission."""
from pathlib import Path
import json,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from driver_common import gate,parser,require,read_json,public_save,sha,require_tags,main_guard
from m1_v14_observation import canonical_absence

CHANGED={'revision','executable','environment_prefix','package_version','core_version','environment_fingerprint'}

def absent(context):
    from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
    require(WindowsTasks().read(context.C['tasks']['nexus']['name']) is None,'UPGRADE_TASK_ABSENCE_REQUIRED')
    canonical_absence(context,'nexus')

def validate_plan(context,value):
    from okto_nexus.adapters.outbound.service_manager.context import document_revision
    body=value.get('plan',{})
    require(value.get('plan_revision')==document_revision(body) and body.get('component')=='server'
        and body.get('instance_id')==context.C['tasks']['nexus']['instance_id']
        and body.get('source_receipt') is None and body.get('source_claim') is None
        and body.get('source_generation')==context.amendment['migration']['generation'], 'UPGRADE_SCOPE_CHANGED')
    source,target=body['source_context'],body['target_context']
    require(document_revision(source)==context.amendment['migration']['source_context_revision'],
        'UPGRADE_SOURCE_CONTEXT_CHANGED')
    require({k:v for k,v in source.items() if k not in CHANGED}=={k:v for k,v in target.items() if k not in CHANGED},
        'UPGRADE_NON_ENVIRONMENT_CHANGE')
    candidate=body['candidate']
    require(target['executable']==candidate['executable']==context.installed['python']
        and target['environment_prefix']==candidate['environment_prefix']==context.installed['python_prefix']
        and target['package_version']=='0.3.3' and target['core_version']=='0.0.14', 'UPGRADE_TARGET_CHANGED')
    require(target=={**source,'revision':2,'executable':candidate['executable'],
        'environment_prefix':candidate['environment_prefix'],'package_version':candidate['package']['version'],
        'core_version':candidate['core']['version'],'environment_fingerprint':document_revision(candidate)},
        'UPGRADE_TARGET_NOT_CANONICAL')
    return value['plan_revision']

def execute(context,phase):
    absent(context)
    migration=context.amendment['migration']
    for key in ('run','shutdown'):
        pin=migration[key];require(sha(pin['path'])==pin['sha256'],'DRAIN_BASIS_CHANGED')
    plan_path=context.PRIVATE/'environment-upgrade-plan.json'
    argv=[context.installed['python'],'-X','utf8','-I','-B','-m','okto_nexus.adapters.inbound.cli.main',
        'service','upgrade-'+phase,*context.C['service_selection_args'],'--json']
    if phase=='plan':
        require(sha(migration['source_context']['path'])==migration['source_context']['sha256'],'SOURCE_CONTEXT_CHANGED')
        argv+=['--python',context.installed['python'],'--output',str(plan_path)]
    else:
        value=read_json(plan_path);revision=validate_plan(context,value)
        review=read_json(context.PRIVATE/'environment-upgrade-reviewed.json');require_tags(review,context)
        require(review.get('decision')=='apply' and review.get('plan_sha256')==sha(plan_path)
            and review.get('plan_revision')==revision,'EXACT_UPGRADE_ROOT_REVIEW_REQUIRED')
        argv+=['--plan-file',str(plan_path),'--expected-revision',revision]
    public_save(context,'environment-upgrade-'+phase+'-reserved.json',{'state':'DISPATCH_RESERVED',
        'target_python':context.installed['python'],'service_start':False,'model_reservations':0})
    out=context.PRIVATE/('upgrade-'+phase+'.stdout');err=context.PRIVATE/('upgrade-'+phase+'.stderr')
    with out.open('xb') as stdout,err.open('xb') as stderr:
        child=subprocess.Popen(argv,cwd=context.ROOT,env=context.env(),stdin=subprocess.DEVNULL,
            stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        code=child.wait()
    raw=read_json(out)
    result={'returncode':code,'stdout_sha256':sha(out),'stderr_sha256':sha(err),'provider_accessed':False,
        'service_started':False,'reported_code':raw.get('reason',raw.get('code'))}
    if code==0:
        plan=read_json(plan_path);revision=validate_plan(context,plan)
        result.update(plan_sha256=sha(plan_path),plan_revision=revision)
        if phase=='apply':
            require(raw.get('applied') is True and raw.get('plan_revision')==revision,'UPGRADE_APPLY_UNCONFIRMED')
            current=read_json(migration['source_context']['path'])
            require(current==plan['plan']['target_context'],'UPGRADE_CONTEXT_NOT_PUBLISHED')
            result.update(applied=True,context_sha256=sha(migration['source_context']['path']))
    public_save(context,'environment-upgrade-'+phase+'-result.json',result)
    return code

def main():
    p=parser();p.add_argument('phase',choices=['plan','apply']);args=p.parse_args()
    return execute(gate(args),args.phase)
if __name__=='__main__':raise SystemExit(main_guard(main))
