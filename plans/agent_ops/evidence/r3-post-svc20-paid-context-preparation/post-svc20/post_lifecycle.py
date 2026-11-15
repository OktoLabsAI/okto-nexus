"""One new canonical start; subsequent capture/watch/cleanup reuse frozen functions."""
import subprocess
from post_context import require,read_json,sha,connector,observed

def start(X,*,popen=subprocess.Popen):
    require(not (X.PUBLIC/'connector-start-reserved.json').exists(),'START_ALREADY_RESERVED')
    proof=X.require_pre_start()
    if not X.PUBLIC.exists():observed.secure_directory(X.PUBLIC,X.CONTROL)
    if not X.PRIVATE.exists():observed.secure_directory(X.PRIVATE,X.CONTROL)
    argv=connector.commands(X)['start']
    X.save('connector-start-reserved.json',{'state':'RESERVED_BEFORE_DISPATCH','argv':argv,'pre_start':proof,
        'basis_svc20_result_sha256':X.post_plan['basis']['svc20_result']['sha256'],'reinstall_selected':False,'provider_calls_selected':0})
    # Revalidate after durable reservation. Refusal consumes this selection, never retries.
    X.require_pre_start()
    with (X.PRIVATE/'connector-start.stdout').open('xb') as out,(X.PRIVATE/'connector-start.stderr').open('xb') as err:
        child=popen(argv,cwd=X.ROOT,env=X.connector_env(),stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                    creationflags=subprocess.CREATE_NO_WINDOW)
        code=child.wait()
    result={'returncode':code,'stdout_sha256':sha(X.PRIVATE/'connector-start.stdout'),
        'stderr_sha256':sha(X.PRIVATE/'connector-start.stderr'),'physical_exit_confirmed':False,
        'basis_svc20_result_sha256':X.post_plan['basis']['svc20_result']['sha256'],'reinstall_selected':False}
    try:
        raw=read_json(X.PRIVATE/'connector-start.stdout');value=raw.get('data',raw)
        result['projection']={k:value.get(k) for k in ('state','reason','code','pid','generation','instance_id') if k in value}
    except (ValueError,TypeError,AttributeError):result['parse_error']='CLI_JSON_UNCONFIRMED'
    X.save('connector-start-returned.json',result)
    require(code==0 and not result.get('parse_error'),'CONNECTOR_START_UNCONFIRMED_NO_REPLAY')
    return result

def select(X):
    receipt=read_json(X.PUBLIC/'connector-start-returned.json');X.require_tags(receipt)
    require(receipt.get('returncode')==0 and not receipt.get('parse_error'),'POST_START_UNCONFIRMED')
    result,handles=connector.capture(X)
    try:
        old=X.values['after_connect']
        require(result['generation']!=old['generation'] and result['cohort']['cycle_id']!=old['cohort']['cycle_id'], 'FRESH_POST_SVC20_COHORT_REQUIRED')
        X.save('connector-owner-selection.json',result)
        return result
    finally:
        for h in handles.values():h.close()

def cleanup(X):
    value=connector.cleanup_valid(X);X.save('connector-cleanup.json',value);return value

def dispatch(X,action):
    if action=='start':return start(X)
    if action=='select':return select(X)
    if action=='watch':return connector.watch(X)
    if action=='stop':return connector.normal_stop(X)
    if action=='cleanup':return cleanup(X)
    if action=='uninstall':return connector.lifecycle(X,'uninstall')
    raise RuntimeError('POST_SVC20_ACTION_INVALID')
