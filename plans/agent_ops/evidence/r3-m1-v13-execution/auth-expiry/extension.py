"""One explicit read-only review after the retained available grant expires."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,os,sys,time

HERE=Path(__file__).resolve().parent
def require(value,code):
    if not value:raise ValueError(code)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def load_pinned(name,pin):
    require(sha(pin['path'])==pin['sha256'],'EXTENSION_PIN_CHANGED')
    spec=importlib.util.spec_from_file_location(name,pin['path']);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module

def verify_manifest(path,digest):
    require(sha(path)==digest,'EXTENSION_MANIFEST_CHANGED');m=read(path)
    require(m['scope']=='ONE_EXPLICIT_READONLY_REVIEW_AFTER_EXPIRY','EXTENSION_SCOPE_CHANGED')
    for key in ('extension','execute_copy','original_authorize','publication'):
        require(sha(m[key]['path'])==m[key]['sha256'],'EXTENSION_PIN_CHANGED')
    require(Path(m['extension']['path']).resolve()==Path(__file__).resolve(),'EXTENSION_ORIGIN_CHANGED')
    return m

def authority(context,m):
    from driver_common import require_tags
    require(context.args.expected_proposal_sha256==m['proposal_sha256']
        and context.args.approval_sha256==m['approval_sha256']
        and str(context.CONTROL)==m['control_root'],'AUTHORITY_CHANGED')
    require(sha(m['original_import_review_returned']['path'])==m['original_import_review_returned']['sha256'],'IMPORT_REVIEW_CHANGED')
    result=read(m['original_import_review_returned']['path']);require_tags(result,context)
    require(result['mode']=='authorize_local' and result['selection']==['review']
        and result['returncode']==0 and result['wrapper_exit_confirmed'] is True,'FIRST_REVIEW_EXIT_REQUIRED')

def before_review(context,m,*,now=None,child=False):
    from driver_common import require_tags
    authority(context,m)
    for key in ('old_public_review','old_work_checkpoint','old_controller'):
        pin=m[key];require(sha(pin['path'])==pin['sha256'],'PRIOR_REVIEW_OR_CHECKPOINT_CHANGED')
    old=read(m['old_public_review']['path']);require_tags(old,context)
    require(old['status']=='EXISTING_GRANT_AVAILABLE' and old['model_admissions']==0
        and old['calls']=={'review':1} and old['two_work_window_available'] is False,'FIRST_AVAILABLE_REVIEW_REQUIRED')
    review=old['review'];grant=review['current_grants'][0]
    require(len(review['current_grants'])==1 and review['has_more_grants'] is False
        and review['total_grants']==1 and grant['state']=='available'
        and grant['used_executions']==0 and grant['max_executions']==20
        and grant['expires_at']==m['old_expiry'],'UNUSED_AVAILABLE_GRANT_REQUIRED')
    require((now or datetime.now(timezone.utc))>=datetime.fromisoformat(m['old_expiry'].replace('Z','+00:00')),'WAIT_FOR_RETAINED_EXPIRY')
    work=read(m['old_work_checkpoint']['path']);validate_pending(context,m,work.get('authorization'))
    require(not work.get('session_id') and not work.get('work'),'PRIOR_WORK_PRESENT')
    cp=read(m['old_controller']['path']);require(cp['requests']=={} and cp['faults']==[],'PRIOR_WORK_OR_FAULT')
    require(not any((context.PUBLIC/name).exists() for name in ('authorize-local-apply-reserved.json','authorize-local-apply.json','authorize-local-expired-review-reserved.json','authorize-local-expired-review-unconfirmed.json','authorize-local-review-replacement.json')),'EXTRA_REVIEW_OR_ISSUE_ALREADY_SELECTED')
    require(not (context.PRIVATE/'authorize-local-reviewed.json').exists(),'PRIOR_ISSUE_DECISION_PRESENT')
    ledger=HERE/'runtime-private';reservation=ledger/'authorize_local-review.reserved.json'
    if child:
        value=read(reservation);require_tags(value,context)
        require(value['mode']=='authorize_local' and value['selection']==['review']
            and not (ledger/'authorize_local-review.returned.json').exists(),'EXTENSION_CHILD_SELECTION_INVALID')
    else:require(not reservation.exists(),'EXTRA_REVIEW_ALREADY_RESERVED')
    return old

def validate_pending(context,m,pending):
    old=read(m['old_public_review']['path'])['review']
    require(pending is not None and pending.get('state')=='review'
        and pending.get('review_revision')==old['review_revision']
        and pending.get('review')=={k:v for k,v in old.items() if k!='review_revision'},'EXACT_PRIOR_REVIEW_REQUIRED')

def preserve_history(context,m):
    original=Path(m['old_public_review']['path']);history=context.PUBLIC/'authorize-local-review-history-available.json'
    require(sha(original)==m['old_public_review']['sha256'],'FIRST_REVIEW_CHANGED')
    raw=original.read_bytes()
    if history.exists():require(history.read_bytes()==raw,'FIRST_REVIEW_HISTORY_CHANGED')
    else:
        with history.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return history

def publisher(context,m,digest,driver):
    from driver_common import public_save,tags,reserve
    def publish(selected,name,value):
        require(selected is context,'PUBLICATION_CONTEXT_CHANGED')
        if name!='authorize-local-review.json':
            names={'authorize-local-review-reserved.json':'authorize-local-expired-review-reserved.json',
                'authorize-local-review-unconfirmed.json':'authorize-local-expired-review-unconfirmed.json',
                'authorization-normal-stop-reserved.json':'expired-review-normal-stop-reserved.json'}
            require(name in names,'EXTRA_PUBLICATION_REFUSED')
            return public_save(context,names[name],value)
        driver.validate_review(context,value['review'])  # Canonical expired0/20, not a clock inference.
        require(value['status']=='EXPIRED_UNUSED_GRANT_REVIEWED' and value['model_admissions']==0
            and value['calls']=={'review':1},'EXPIRED_READONLY_REVIEW_REQUIRED')
        prior=read(m['old_public_review']['path'])['review']
        current=value['review']
        require(current['scope']==prior['scope'] and current['current_grants'][0]['grant_id']==prior['current_grants'][0]['grant_id']
            and current['current_grants'][0]['expires_at']==m['old_expiry']
            and current['request']['client_request_id']!=prior['request']['client_request_id'],'REVIEW_SCOPE_OR_GRANT_CHANGED')
        history=preserve_history(context,m)
        value={**value,'supersedes_review_sha256':m['old_public_review']['sha256'],
            'review_extension_manifest_sha256':digest,'explicit_readonly_requery':True,**tags(context)}
        raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
        target=context.PUBLIC/name;pending=target.with_name('authorize-local-expired-review.pending')
        transition={'old_sha256':m['old_public_review']['sha256'],'new_sha256':hashlib.sha256(raw).hexdigest(),
            'history_path':str(history),'history_sha256':sha(history),'extension_manifest_sha256':digest,
            'old_review_revision':prior['review_revision'],'new_review_revision':current['review_revision'],
            'reason':'One explicit read-only canonical requery after the retained available grant expired; original evidence unchanged.',
            'model_admissions':0,'grant_issued':False}
        public_save(context,'authorize-local-review-replacement-reserved.json',transition)
        with pending.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        require(sha(target)==transition['old_sha256'],'CURRENT_REVIEW_CHANGED_BEFORE_REPLACE')
        os.replace(pending,target)
        public_save(context,'authorize-local-review-replacement.json',transition|{'status':'CURRENT_REVIEW_REPLACED_WITH_HISTORY'})
        return target
    return publish

def execute_child(context,m,digest):
    before_review(context,m,child=True)
    preserve_history(context,m)
    load_pinned('publication',m['publication'])
    driver=load_pinned('expired_review_execute_copy',m['execute_copy'])
    driver.validate_retained_pending=lambda c,pending:validate_pending(c,m,pending)
    driver.public_save=publisher(context,m,digest,driver)
    result=driver.execute(context,'review');print(json.dumps(result));return 0

def exit_proof(context,m,digest):
    from driver_common import public_save,require_tags
    authority(context,m);directory=HERE/'runtime-private'
    reservation=read(directory/'authorize_local-review.reserved.json');returned=read(directory/'authorize_local-review.returned.json')
    require_tags(reservation,context);require_tags(returned,context)
    require(reservation['mode']==returned['mode']=='authorize_local'
        and reservation['selection']==returned['selection']==['review'] and returned['wrapper_exit_confirmed'] is True,'EXTENSION_EXIT_UNCONFIRMED')
    for key in ('stdout','stderr'):require(sha(directory/('authorize_local-review.'+key))==returned[key+'_sha256'],'EXTENSION_OUTPUT_CHANGED')
    evidence={'status':'EXPIRED_REVIEW_EXTENSION_EXIT_CONFIRMED','extension_manifest_sha256':digest,
        'reservation_sha256':sha(directory/'authorize_local-review.reserved.json'),'returned_sha256':sha(directory/'authorize_local-review.returned.json'),
        'returncode':returned['returncode'],'original_available_review_sha256':m['old_public_review']['sha256'],
        'history_sha256':sha(context.PUBLIC/'authorize-local-review-history-available.json'),
        'replacement_sha256':sha(context.PUBLIC/'authorize-local-review-replacement.json') if (context.PUBLIC/'authorize-local-review-replacement.json').exists() else None,
        'current_review_sha256':sha(context.PUBLIC/'authorize-local-review.json'),'model_admissions':0,'grant_issued_by_this_extension':False}
    path=public_save(context,'authorize-expired-review-extension-exits.json',evidence)
    print(json.dumps({'path':str(path),'sha256':sha(path),'status':evidence['status']}));return 0

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--child',action='store_true')
    for name in ('proposal','expected-proposal-sha256','approval-path','approval-sha256'):p.add_argument('--'+name,required=True)
    p.add_argument('phase',choices=['review','verify-exits']);args=p.parse_args();m=verify_manifest(args.manifest,args.manifest_sha256)
    sys.path.insert(0,str(Path(m['original_authorize']['path']).parent))
    from driver_common import gate,secure_directory
    context=gate(args)
    if args.phase=='verify-exits':require(not args.child,'CHILD_MODE_INVALID');return exit_proof(context,m,args.manifest_sha256)
    if args.child:return execute_child(context,m,args.manifest_sha256)
    before_review(context,m)
    import invoke
    original=invoke.select
    def selected(c,mode,selection):
        require(mode=='authorize_local' and selection==['review'],'ONLY_ONE_READONLY_REVIEW')
        argv,stdin=original(c,mode,selection)
        require(stdin is None and argv[3]==m['original_authorize']['path'],'ORIGINAL_SELECTION_CHANGED')
        return [*argv[:3],str(Path(__file__)),'--manifest',args.manifest,'--manifest-sha256',args.manifest_sha256,'--child',*argv[4:]],None
    invoke.select=selected
    try:result=invoke.dispatch(context,'authorize_local',['review'],secure_directory(HERE/'runtime-private',HERE))
    finally:invoke.select=original
    print(json.dumps(result));return result['returncode']

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'status':'EXPIRED_REVIEW_EXTENSION_REFUSED','code':str(error) if type(error) is ValueError else type(error).__name__}));raise SystemExit(2)
