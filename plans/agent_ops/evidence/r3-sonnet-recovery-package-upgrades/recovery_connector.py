"""Connector own-task lifecycle and retained supervisor cohort, no provider submit."""
from pathlib import Path
import json
import os
import subprocess
import time

from recovery_context import require,read_json,sha,reserve
from recovery_observation import Process,ROLES,status,same_owner,same_cycle,canonical_absence


def installation(X):
    from okto_nexus_connector.platform.user_service import UserService
    return UserService(Path(X.P['paths']['connector_state']))


def normalize_identity(value):
    require(isinstance(value,dict) and type(value.get('pid')) is int and value['pid']>0,
        'CONNECTOR_COHORT_INCOMPLETE')
    token=value.get('birth_token')
    require(isinstance(token,str) and token.startswith('filetime:')
        and token[9:].isascii() and token[9:].isdigit(), 'CONNECTOR_BIRTH_TOKEN_INVALID')
    birth=int(token[9:])
    require(birth>0 and token=='filetime:'+str(birth), 'CONNECTOR_BIRTH_TOKEN_NONCANONICAL')
    return {'pid':value['pid'],'birth':birth}


def cycle(X):
    from okto_nexus_connector.platform.service_supervision import read_cycle
    service=installation(X)
    value=read_cycle(service.root,service.receipt())
    require(isinstance(value,dict),'CONNECTOR_CYCLE_MISSING')
    result={k:value.get(k) for k in ('cycle_id','phase','attempts_started','child_acknowledged')}
    for role in ROLES:
        v=value.get(role)
        result[role]=normalize_identity(v)
    return result


def capture(X,*,observe=status,read_cycle=cycle,process=Process):
    before=observe(X,'connector');c=read_cycle(X)
    require(c['phase']=='running' and c['child_acknowledged'] is True
        and c['child']['pid']==before['pid'],'CONNECTOR_ACK_REQUIRED')
    handles={}
    try:
        for role in ROLES:
            h=process(c[role]['pid']);handles[role]=h
            require(h.birth==c[role]['birth'] and h.image in X.installed['python_images']
                and sha(h.image)==X.installed['python_images'][h.image],'CONNECTOR_PROCESS_IDENTITY_CHANGED')
        require(read_cycle(X)==c,'CONNECTOR_CYCLE_CHANGED_DURING_CAPTURE')
        same_owner(before,observe(X,'connector'))
        require(not any(h.exited() for h in handles.values()),'CONNECTOR_EXIT_DURING_CAPTURE')
        return {**before,'cohort':c,'selected_at':time.time()},handles
    except BaseException:
        for h in handles.values():h.close()
        raise


def current_ready(X):
    selected=read_json(X.PUBLIC/'connector-owner-selection.json');X.require_tags(selected)
    started=read_json(X.PUBLIC/'connector-exit-watch-started.json');X.require_tags(started)
    require(started['cohort']==selected['cohort'] and started['retained_roles']==list(ROLES)
        and not (X.PUBLIC/'connector-exit-proof.json').exists()
        and not (X.PUBLIC/'connector-exit-watch-timeout.json').exists(),'LIVE_CONNECTOR_WATCH_REQUIRED')
    h=Process(started['observer']['pid'])
    try:
        require(h.birth==started['observer']['birth'] and h.image in X.installed['python_images']
            and sha(h.image)==X.installed['python_images'][h.image],'CONNECTOR_OBSERVER_CHANGED')
    finally:h.close()
    same_owner(selected,status(X,'connector'));now=cycle(X);same_cycle(selected['cohort'],now)
    require(now['phase']=='running' and now['child_acknowledged'] is True,'CONNECTOR_NOT_READY')
    return selected


def stop_argv(X):
    return [X.python,'-I','-B','-X','utf8','-m','okto_nexus_connector.cli.main','--non-interactive','--json',
        '--state-dir',X.P['paths']['connector_state'],'daemon','stop','--timeout','45']


def commands(X):
    base=[X.python,'-I','-B','-X','utf8','-m','okto_nexus_connector.cli.main','--non-interactive','--json',
        '--state-dir',X.P['paths']['connector_state']]
    return {'install':base+['service','install'],'start':base+['daemon','start','--timeout','45'],
        'stop':stop_argv(X),'uninstall':base+['service','uninstall']}


def cleanup_valid(X):
    proof=read_json(X.PUBLIC/'connector-exit-proof.json');X.require_tags(proof)
    selected=read_json(X.PUBLIC/'connector-owner-selection.json');X.require_tags(selected)
    require(proof['cohort']==selected['cohort'] and set(proof['exits'])==set(ROLES),'CONNECTOR_EXIT_PROOF_SCOPE_CHANGED')
    require(all(proof['exits'][r]['physical_exit'] is True and
        proof['exits'][r]['pid']==selected['cohort'][r]['pid'] and
        proof['exits'][r]['birth']==selected['cohort'][r]['birth'] for r in ROLES),'ALL_CONNECTOR_EXITS_REQUIRED')
    _,task=installation(X).observe()
    require(task is not None and not task.active,'CONNECTOR_NATIVE_NOT_INACTIVE')
    absent=canonical_absence(X,'connector')
    return {'cohort':selected['cohort'],'native_inactive':True,'canonical_absence':absent,'work_settlement_claimed':False}


def lifecycle(X,action):
    require(action in commands(X),'CONNECTOR_ACTION_INVALID')
    if action=='install':
        X.require_nexus_ready();X.require_migrated('connector');canonical_absence(X,'connector')
        _,task=installation(X).observe();require(task is None,'CONNECTOR_TASK_ALREADY_EXISTS')
    elif action=='start':
        previous=read_json(X.PUBLIC/'connector-install-returned.json');X.require_tags(previous)
        require(previous['returncode']==0,'CONNECTOR_INSTALL_NOT_CONFIRMED')
    elif action=='stop':current_ready(X)
    else:
        proof=read_json(X.PUBLIC/'connector-cleanup.json');X.require_tags(proof);cleanup_valid(X)
    before=None
    if action=='uninstall':
        from okto_nexus_connector.platform.paths import state_file
        state=state_file(Path(X.P['paths']['connector_state']))
        before={'path':str(state),'exists':state.exists(),
            'sha256':sha(state) if state.exists() else None,'bytes':state.stat().st_size if state.exists() else None}
    argv=commands(X)[action]
    X.save(f'connector-{action}-reserved.json',{'state':'RESERVED_BEFORE_DISPATCH','argv':argv,'provider_calls':0})
    with (X.PRIVATE/f'connector-{action}.stdout').open('xb') as out,(X.PRIVATE/f'connector-{action}.stderr').open('xb') as err:
        child=subprocess.Popen(argv,cwd=X.ROOT,env=X.connector_env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        rc=child.wait()
    raw=read_json(X.PRIVATE/f'connector-{action}.stdout');data=raw.get('data',raw)
    value={'returncode':rc,'projection':{k:data.get(k) for k in ('state','reason','code','pid','generation','instance_id','shutdown_outcome') if k in data},
        'stdout_sha256':sha(X.PRIVATE/f'connector-{action}.stdout'),'stderr_sha256':sha(X.PRIVATE/f'connector-{action}.stderr'),
        'physical_exit_confirmed':False}
    X.save(f'connector-{action}-returned.json',value)
    if action=='uninstall' and rc==0:
        _,task=installation(X).observe();require(task is None,'CONNECTOR_TASK_REMAINS')
        canonical_absence(X,'connector')
        state=Path(before['path'])
        require(state.exists()==before['exists'] and (not state.exists() or sha(state)==before['sha256']),
            'CONNECTOR_DATA_CHANGED_BY_UNINSTALL')
        X.save('connector-final-presence.json',{'task_absent':True,'data_preserved':True,'data':before,'force_used':False})
    return value


def normal_stop(X):
    return lifecycle(X,'stop')


def select(X):
    receipt=read_json(X.PUBLIC/'connector-start-returned.json');X.require_tags(receipt)
    require(receipt['returncode']==0,'CONNECTOR_START_UNCONFIRMED')
    selected,handles=capture(X)
    try:X.save('connector-owner-selection.json',selected)
    finally:
        for h in handles.values():h.close()
    return selected


def watch(X):
    selected=read_json(X.PUBLIC/'connector-owner-selection.json');X.require_tags(selected)
    now,handles=capture(X);same_cycle(selected['cohort'],now['cohort'])
    own=Process(os.getpid())
    try:
        X.save('connector-exit-watch-started.json',{'cohort':now['cohort'],'retained_roles':list(ROLES),
            'observer':{'pid':own.pid,'birth':own.birth},'terminate_right':False})
        deadline=time.monotonic()+3600
        while time.monotonic()<deadline:
            if all(h.exited() for h in handles.values()):
                value={'cohort':now['cohort'],'observed_at':time.time(),'force_used':False,
                    'exits':{r:{'pid':h.pid,'birth':h.birth,'physical_exit':True,'exit_code':h.exit_code()} for r,h in handles.items()}}
                X.save('connector-exit-proof.json',value);return value
            time.sleep(.2)
        X.save('connector-exit-watch-timeout.json',{'physical_exit_confirmed':False,'cohort':now['cohort']})
        raise RuntimeError('CONNECTOR_EXIT_WATCH_TIMEOUT')
    finally:
        own.close()
        for h in handles.values():h.close()
