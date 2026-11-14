"""Finite import reconciliation for the original v13 authorize review/apply."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,code):
    if not value:raise ValueError(code)
def read(path):return json.loads(Path(path).read_bytes())

def verify_manifest(path,expected):
    require(sha(path)==expected,'SUPPLEMENT_MANIFEST_CHANGED');m=read(path)
    require(m['scope']=='V13_AUTHORIZE_IMPORT_RECONCILIATION_ONLY','SUPPLEMENT_SCOPE_CHANGED')
    for key in ('shim','supplement','original_authorize','publication'):
        pin=m[key];require(sha(pin['path'])==pin['sha256'],'SUPPLEMENT_PIN_CHANGED')
    require(Path(m['supplement']['path']).resolve()==Path(__file__).resolve(),'SUPPLEMENT_ORIGIN_CHANGED')
    return m

def common(context,manifest):
    from driver_common import require_tags
    require(context.args.expected_proposal_sha256==manifest['proposal_sha256']
        and context.args.approval_sha256==manifest['approval_sha256'],'ORIGINAL_AUTHORITY_CHANGED')
    require(str(context.CONTROL)==manifest['control_root'],'CONTROL_ROOT_CHANGED')
    for key,pin in manifest['failed_attempt'].items():
        require(sha(pin['path'])==pin['sha256'],'ORIGINAL_FAILED_ATTEMPT_CHANGED')
    result=read(manifest['failed_attempt']['returned']['path']);require_tags(result,context)
    require(result['mode']=='authorize_local' and result['selection']==['review']
        and result['returncode']==1 and result['wrapper_exit_confirmed'] is True
        and result['stderr_sha256']==manifest['failed_attempt']['stderr']['sha256']
        and result['stdout_sha256']==manifest['failed_attempt']['stdout']['sha256'],'ORIGINAL_FAILURE_NOT_PREIMPORT')
    require(sha(context.PUBLIC/'adopt-local-result.json')==manifest['adoption_sha256'],'ADOPTION_CHANGED')

def review_before_dispatch(context,manifest):
    common(context,manifest)
    require(sha(context.PRIVATE/'controller.json')==manifest['before_controller_sha256'],'CONTROLLER_CHANGED_BEFORE_RECONCILIATION')
    checkpoint=read(context.PRIVATE/'controller.json')
    require(checkpoint['requests']=={} and checkpoint['faults']==[], 'PRIOR_PRODUCTIVE_EFFECT_OR_FAULT')
    require(not any(p.name.startswith('authorize-local-') for folder in (context.PUBLIC,context.PRIVATE)
        for p in folder.iterdir()),'AUTHORIZATION_EFFECT_ALREADY_SELECTED')
    require(sha(context.P['adoption']['profile_pin']['path'])==context.P['adoption']['profile_pin']['sha256'],'PROFILE_CHANGED_BEFORE_RECONCILIATION')

def supplemental_return(context,phase):
    from driver_common import require_tags
    directory=HERE/'runtime-private';name='authorize_local-'+phase
    reserve=directory/(name+'.reserved.json');returned=directory/(name+'.returned.json')
    a,b=read(reserve),read(returned);require_tags(a,context);require_tags(b,context)
    require(a['mode']==b['mode']=='authorize_local' and a['selection']==b['selection']==[phase]
        and b['wrapper_exit_confirmed'] is True,'SUPPLEMENT_CHILD_EXIT_UNCONFIRMED')
    require(sha(directory/(name+'.stdout'))==b['stdout_sha256'] and sha(directory/(name+'.stderr'))==b['stderr_sha256'],'SUPPLEMENT_OUTPUT_CHANGED')
    return {'reservation_sha256':sha(reserve),'returned_sha256':sha(returned),'returncode':b['returncode'],'wrapper_exit_confirmed':True}

def apply_before_dispatch(context,manifest):
    common(context,manifest)
    require(supplemental_return(context,'review')['returncode']==0,'SUPPLEMENT_REVIEW_UNCONFIRMED')
    require(not any((Path(manifest['original_authorize']['path']).parent/'runtime-private'/('authorize_local-apply'+suffix)).exists()
        for suffix in ('.reserved.json','.returned.json')),'ORIGINAL_APPLY_ALREADY_SELECTED')
    require(not (context.PUBLIC/'authorize-local-apply-reserved.json').exists()
        and not (context.PUBLIC/'authorize-local-apply.json').exists(),'APPLY_ALREADY_SELECTED')
    # Original execute still validates canonical expired0/20, exact root review,
    # current checkpoint/CAS, recover-before-issue and current owner/freshness.

def validate_child(context,manifest,phase):
    from driver_common import require_tags
    require(sha(manifest['supplement']['path'])==manifest['supplement']['sha256'],'SUPPLEMENT_PIN_CHANGED')
    path=HERE/'runtime-private'/('authorize_local-'+phase+'.reserved.json')
    reservation=read(path);require_tags(reservation,context)
    require(reservation['mode']=='authorize_local' and reservation['selection']==[phase]
        and not path.with_name(path.name.replace('.reserved.json','.returned.json')).exists(),'CHILD_SELECTION_INVALID')
    if phase=='review':review_before_dispatch(context,manifest)
    else:apply_before_dispatch(context,manifest)

def select_shim(original_select,context,mode,selection,manifest,manifest_path,manifest_sha):
    require(mode=='authorize_local' and selection in (['review'],['apply']),'SUPPLEMENT_SELECTION_INVALID')
    argv,stdin=original_select(context,mode,selection)
    require(stdin is None and argv[:4]==[context.P['package_pins']['python'],'-I','-B',manifest['original_authorize']['path']], 'ORIGINAL_SELECTION_CHANGED')
    return [*argv[:3],manifest['shim']['path'],'--manifest',str(manifest_path),'--manifest-sha256',manifest_sha,*argv[4:]],None

def exit_proof(context,manifest,manifest_sha):
    common(context,manifest)
    directory=HERE/'runtime-private'
    names={p.name for p in directory.glob('*.reserved.json')}
    require('authorize_local-review.reserved.json' in names
        and names <= {'authorize_local-review.reserved.json','authorize_local-apply.reserved.json'},'SUPPLEMENT_SELECTION_UNCONFIRMED')
    proofs={phase:supplemental_return(context,phase) for phase in ('review','apply')
        if (directory/('authorize_local-'+phase+'.reserved.json')).exists()}
    return {'status':'SUPPLEMENT_WRAPPERS_EXIT_CONFIRMED','supplement_manifest_sha256':manifest_sha,
        'original_failed_attempt':manifest['failed_attempt'],'original_failure_preserved':True,
        'original_review_returncode':1,'supplemental_authorization_selections':proofs,
        'scope':'Only original authorize review/apply with explicitly preloaded pinned publication; no model reservation or setup replay. Returned error remains error; exit proof is not authorization success.',
        'cleanup_requirement':'Retain and bind this proof alongside original final-presence and closure; neither original failed selection nor supplemental failure is relabeled.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--proposal',required=True);p.add_argument('--expected-proposal-sha256',required=True)
    p.add_argument('--approval-path',required=True);p.add_argument('--approval-sha256',required=True)
    p.add_argument('phase',choices=['review','apply','verify-exits']);args=p.parse_args()
    manifest=verify_manifest(args.manifest,args.manifest_sha256)
    sys.path.insert(0,str(Path(manifest['original_authorize']['path']).parent))
    from driver_common import gate,secure_directory,public_save
    context=gate(args)
    if args.phase=='verify-exits':
        value=exit_proof(context,manifest,args.manifest_sha256)
        path=public_save(context,'authorize-import-supplement-exits.json',value)
        print(json.dumps({'status':value['status'],'path':str(path),'sha256':sha(path)}));return 0
    if args.phase=='review':review_before_dispatch(context,manifest)
    else:apply_before_dispatch(context,manifest)
    import invoke
    original=invoke.select
    invoke.select=lambda c,m,s:select_shim(original,c,m,s,manifest,args.manifest,args.manifest_sha256)
    try:result=invoke.dispatch(context,'authorize_local',[args.phase],secure_directory(HERE/'runtime-private',HERE))
    finally:invoke.select=original
    print(json.dumps(result));return result['returncode']

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'status':'SUPPLEMENT_REFUSED','code':str(error) if type(error) is ValueError else type(error).__name__}));raise SystemExit(2)
