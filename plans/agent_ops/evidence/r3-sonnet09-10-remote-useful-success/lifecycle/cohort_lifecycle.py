"""Finite start/observe/normal-stop on already upgraded own tasks, no paid work."""
from pathlib import Path
import importlib.util,json,subprocess,time
from recovery_context import require,read_json,sha,pin,reserve
import recovery_observation as O
import recovery_connector as C
import recovery_nexus as N

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module

def binding_basis(X):
    done=X.done;binding=read_json(pin(X.P['binding_ancestry']))
    require(done.get('current_credential_epoch')==2 and done.get('material_status')=='reuse_existing','DONE_EPOCH2_REQUIRED')
    profile=Path(X.P['profile_ancestry']['path']);require(sha(profile)==X.P['profile_ancestry']['sha256'],'PROFILE_CHANGED')
    guards=load('fresh_binding_ancestry',pin(X.P['binding_guard']))
    guards.validate_done(read_json(profile),binding,read_json(pin(binding['draft'])))
    pin(done['canonical_review_pin']);pin(done['rotation_import_result_pin'])
    from okto_nexus_connector.platform.paths import state_file
    from okto_nexus_connector.storage.state_store import StateStore
    state=StateStore(state_file(Path(X.P['paths']['connector_state']))).load()
    identity=state.identity_for(done['server_id'],done['remote_scope']['agent_id'])
    require(identity is not None and identity.credential_epoch==2 and identity.revoked is False
            and state.preferences.get('vault.fallback_file.approved') is True,'SAME_EPOCH2_IDENTITY_REQUIRED')

def physical(proof,selected):
    require(proof['cohort']==selected['cohort'] and set(proof['exits'])==set(O.ROLES),'PRIOR_COHORT_PROOF_CHANGED')
    for role in O.ROLES:
        actual=proof['exits'][role];expected=selected['cohort'][role]
        require(actual.get('physical_exit') is True and actual['pid']==expected['pid']
                and actual['birth']==expected['birth'],'EXACT_PHYSICAL_EXIT_REQUIRED')

def old_exit(X,component):
    selected=read_json(pin(X.P['old_selections'][component]));proof=read_json(pin(X.P['old_exits'][component]))
    physical(proof,selected);return selected

def pre_start(X,component):
    binding_basis(X);X.require_migrated(component);old_exit(X,component)
    service=O.installation(X) if component=='nexus' else C.installation(X)
    _,task=service.observe()
    require(task is not None and task.enabled and not task.active and task.state!=0
        and task.digest==X.C['tasks'][component]['digest'],'SAME_UPGRADED_INACTIVE_TASK_REQUIRED')
    O.canonical_absence(X,component)
    if component=='nexus':N.port_free(X)
    else:X.require_nexus_ready()

def prepare(X):
    require(not X.PUBLIC.exists() and not X.PRIVATE.exists(),'PREPARATION_ALREADY_EXISTS')
    for component in ('nexus','connector'):
        X.require_migrated(component);old_exit(X,component)
        service=O.installation(X) if component=='nexus' else C.installation(X)
        _,task=service.observe()
        require(task is not None and not task.active and task.state!=0
            and task.digest==X.C['tasks'][component]['digest'],'UPGRADED_TASK_NOT_INACTIVE')
        O.canonical_absence(X,component)
    X.PUBLIC.mkdir();O.secure_directory(X.PRIVATE,X.CONTROL)
    X.save('preparation.json',{'status':'PREPARED_EXISTING_Q_TASKS','provider_calls':0,'service_effects':0})
    return {'status':'PREPARED','provider_calls':0}

def command(X,component,action):
    if component=='connector':return C.commands(X)[action]
    return next(x['argv'] for x in X.C['steps'] if x['component']==component and x['action']==action)

def lifecycle(X,component,action):
    require(component in ('nexus','connector') and action in ('start','stop'),'FINITE_ACTION_REQUIRED')
    X.require_tags(read_json(X.PUBLIC/'preparation.json'))
    if action=='start':pre_start(X,component)
    else:(O.current_ready if component=='nexus' else C.current_ready)(X)
    argv=command(X,component,action);require('--force' not in argv,'NO_FORCE_SELECTED')
    name=component+'-'+action
    X.save(name+'-reserved.json',{'status':'RESERVED_BEFORE_DISPATCH','argv':argv,'provider_calls':0})
    if action=='start':pre_start(X,component)
    with (X.PRIVATE/(name+'.stdout')).open('xb') as out,(X.PRIVATE/(name+'.stderr')).open('xb') as err:
        child=subprocess.Popen(argv,cwd=X.ROOT,env=X.connector_env() if component=='connector' else X.env(),
            stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        code=child.wait()  # Keep the wrapper/child; never terminate or replay a pending command.
    result={'returncode':code,'provider_calls':0,'stdout_sha256':sha(X.PRIVATE/(name+'.stdout')),
            'stderr_sha256':sha(X.PRIVATE/(name+'.stderr')),'physical_exit_confirmed':False}
    try:
        raw=read_json(X.PRIVATE/(name+'.stdout'));raw=raw.get('data',raw)
        result['projection']={k:raw.get(k) for k in ('state','reason','code','pid','generation','instance_id',
            'shutdown_outcome','ready_for_queries','observed_owner','transport_failure') if k in raw}
    except (ValueError,TypeError,AttributeError):result['parse_error']='CANONICAL_RESULT_UNCONFIRMED'
    X.save(name+'-returned.json',result);return result

def select(X,component):
    returned=read_json(X.PUBLIC/(component+'-start-returned.json'));X.require_tags(returned)
    require(returned['returncode']==0,'START_UNCONFIRMED_NO_REPLAY')
    capture=O.capture if component=='nexus' else C.capture
    chosen,handles=capture(X)
    try:
        old=old_exit(X,component)
        require(chosen['generation']!=old['generation'] and chosen['cohort']['cycle_id']!=old['cohort']['cycle_id'],
                'FRESH_GENERATION_AND_CYCLE_REQUIRED')
        require(chosen['task']['digest']==X.C['tasks'][component]['digest'],'UPGRADED_TASK_CHANGED')
        X.save(component+'-owner-selection.json',chosen)
        return chosen
    finally:
        for h in handles.values():h.close()

def dispatch(X,component,action):
    if action=='prepare':return prepare(X)
    if action in ('start','stop'):return lifecycle(X,component,action)
    if action=='select':return select(X,component)
    if action=='watch':return (N.watch if component=='nexus' else C.watch)(X)
    if action=='cleanup':
        value=(N.cleanup_valid if component=='nexus' else C.cleanup_valid)(X)
        X.save(component+'-cleanup.json',value);return value
    raise RuntimeError('ACTION_NOT_SELECTED')
