"""Selected own Server lifecycle/operator bootstrap only. Never provider work."""
from pathlib import Path
import argparse
import json
import os
import socket
import subprocess
import time

from recovery_context import Context, require, read_json, pin, sha, public_save, require_tags
from recovery_observation import (Process, installation, capture, cycle, same_cycle,
    current_ready, status, canonical_absence, secure_directory, ROLES)


def preparation(X):
    require(not X.PUBLIC.exists() and not X.PRIVATE.exists(), 'PREPARATION_ALREADY_SELECTED')
    X.require_migrated('nexus')
    predecessor=read_json(pin(X.P['predecessor']))
    require(predecessor['status']=='PASS_SCOPED' and predecessor['task_absent'] is True
        and predecessor['cohort_exit_confirmed'] is True,'CLOSED_PREDECESSOR_REQUIRED')
    for path, value in predecessor['selected_data_retained'].items():
        require(Path(path).resolve().is_relative_to(X.ROOT.resolve())
            and sha(path)==value['sha256'],'PREDECESSOR_DATA_CHANGED')
    for item in X.installed['files']:
        pin(item)
    X.PUBLIC.mkdir()
    secure_directory(X.PRIVATE, X.CONTROL)
    public_save(X, 'preparation.json', {'status':'PREPARED','payload_count':len(X.installed['files']),
        'model_admissions':0,'service_effects':False})
    return {'status':'PREPARED'}


def task_absent(X):
    _, task = installation(X).observe()
    require(task is None, 'OWN_TASK_ALREADY_EXISTS')
    return True


def port_free(X):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(('127.0.0.1',58631))
    return True


def result(X, action):
    value = read_json(X.PUBLIC/f'{action}-returned.json')
    require_tags(value,X)
    require(value['returncode']==0, 'PRIOR_CLI_FAILED')
    return value


def cleanup_valid(X):
    proof=read_json(X.PUBLIC/'nexus-exit-proof.json'); require_tags(proof,X)
    selected=read_json(X.PUBLIC/'nexus-owner-selection.json');require_tags(selected,X)
    require(proof['cohort']==selected['cohort'] and set(proof['exits'])==set(ROLES), 'COHORT_EXIT_MISMATCH')
    require(all(proof['exits'][r]['physical_exit'] is True and
        proof['exits'][r]['pid']==selected['cohort'][r]['pid'] and
        proof['exits'][r]['birth']==selected['cohort'][r]['birth'] for r in ROLES), 'PHYSICAL_EXIT_REQUIRED')
    _, task=installation(X).observe()
    require(task is not None and not task.active, 'NATIVE_TASK_STILL_ACTIVE_OR_MISSING')
    absence=canonical_absence(X,'nexus')
    port_free(X)
    return {'cohort':selected['cohort'],'native_inactive':True,'canonical_absence':absence,'port_free':True,
        'work_settlement_claimed':False,'model_admissions':0}


def lifecycle(X, action):
    require(action in ('install','start','stop','uninstall'),'ACTION_INVALID')
    require_tags(read_json(X.PUBLIC/'preparation.json'),X)
    if action=='install':
        X.require_migrated('nexus');canonical_absence(X,'nexus');task_absent(X);port_free(X)
    elif action=='start':
        result(X,'install'); X.require_migrated('nexus')
    elif action=='stop':
        # No new start or force. Exact selection and current owner still required.
        current_ready(X)
    else:
        require_tags(read_json(X.PUBLIC/'cleanup.json'),X);cleanup_valid(X)
    selected=next(c for c in X.C['steps'] if c['component']=='nexus' and c['action']==action)
    require('--force' not in selected['argv'], 'FORCE_NOT_AUTHORIZED')
    before=None
    if action=='uninstall':
        db=Path(X.P['paths']['server_home'])/'nexus.db'
        before={'path':str(db),'sha256':sha(db),'bytes':db.stat().st_size}
    public_save(X,f'{action}-reserved.json',{'state':'DISPATCH_RESERVED','argv':selected['argv'],'time':time.time(),'model_admissions':0})
    with (X.PRIVATE/f'{action}.stdout').open('xb') as out, (X.PRIVATE/f'{action}.stderr').open('xb') as err:
        child=subprocess.Popen(selected['argv'],cwd=X.ROOT,env=X.env(),stdout=out,stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW)
        rc=child.wait()  # Canonical CLI owns its selected45s timeout; no timeout-kill.
    raw=read_json(X.PRIVATE/f'{action}.stdout')
    projection={k:raw.get(k) for k in ('state','reason','code','pid','generation','instance_id','shutdown_outcome','ready_for_queries') if k in raw}
    value={'returncode':rc,'projection':projection,'stdout_sha256':sha(X.PRIVATE/f'{action}.stdout'),
        'stderr_sha256':sha(X.PRIVATE/f'{action}.stderr'),'completed_at':time.time(),'model_admissions':0}
    public_save(X,f'{action}-returned.json',value)
    if action=='uninstall' and rc==0:
        task_absent(X);port_free(X);canonical_absence(X,'nexus')
        require(sha(before['path'])==before['sha256'],'DATABASE_CHANGED_DURING_UNINSTALL')
        public_save(X,'final-presence.json',{'task_absent':True,'port_free':True,'data':before,'data_preserved':True,'force_used':False})
    return value


def select(X):
    started=read_json(X.PUBLIC/'start-returned.json');require_tags(started,X)
    require(started['returncode']==0,'SUCCESSFUL_START_REQUIRED_FOR_PHASE1')
    chosen,handles=capture(X)
    try:public_save(X,'nexus-owner-selection.json',chosen)
    finally:
        for h in handles.values():h.close()
    return chosen


def watch(X):
    selected=read_json(X.PUBLIC/'nexus-owner-selection.json');require_tags(selected,X)
    chosen,handles=capture(X)
    same_cycle(selected['cohort'],chosen['cohort'])
    own=Process(os.getpid())
    try:
        public_save(X,'nexus-exit-watch-started.json',{'cohort':chosen['cohort'],'retained_roles':list(ROLES),
            'observer':{'pid':own.pid,'birth':own.birth},'terminate_right':False})
        deadline=time.monotonic()+X.P['watch_seconds']
        while time.monotonic()<deadline:
            if all(h.exited() for h in handles.values()):
                value={'cohort':chosen['cohort'],'observed_at':time.time(),'force_used':False,
                    'exits':{r:{'pid':h.pid,'birth':h.birth,'physical_exit':True,'exit_code':h.exit_code()} for r,h in handles.items()}}
                public_save(X,'nexus-exit-proof.json',value)
                return value
            time.sleep(.2)
        public_save(X,'nexus-exit-watch-timeout.json',{'physical_exit_confirmed':False,'cohort':chosen['cohort']})
        raise RuntimeError('PHYSICAL_EXIT_OBSERVER_TIMEOUT')
    finally:
        own.close()
        for h in handles.values():h.close()


def operator(X):
    import operator_bootstrap as boot
    X.require_ready()
    public_save(X,'operator-selection.json',{'state':'SELECTED_ONCE','model_admissions':0})
    deadline=time.monotonic()+X.P['bootstrap_seconds']
    origin,name,login,verify=boot.commands(X)
    observed=boot.http(origin,'GET','/api/v1/operator-auth/status',None,deadline)
    require(observed.get('ok') is True and observed.get('data',{}).get('local') is True,'LOCAL_OPERATOR_STATUS_REQUIRED')
    if observed['data'].get('configured') is True:
        # Existing own account is never reset/rotated; only exact profile status.
        profile=Path(X.P['paths']['operator_home'])/'terminal/operators'/(name+'.json')
        require(profile.is_file(),'EXISTING_ACCOUNT_WITHOUT_OWN_PROFILE_REFUSED')
        X.require_ready()
        value=boot.cli(X,verify,None,deadline)
        require(value.get('state')=='authenticated' and value.get('profile')==name
            and value.get('origin')==origin and value.get('server_id')==X.P['expected_server_id'],'EXISTING_OPERATOR_SCOPE_CHANGED')
        out={'status':'OPERATOR_AUTHENTICATED','profile':name,'origin':origin,'server_id':value['server_id'],
            'account_post_count':0,'login_cli_count':0,'model_admissions':0}
    else:
        require(observed['data'].get('configured') is False,'OPERATOR_CONFIGURATION_UNKNOWN')
        def guard(_):
            require(time.monotonic()<deadline,'OPERATOR_PHASE_DEADLINE')
            X.require_ready()
            return True
        out=boot.bootstrap(X,X.P['expected_server_id'],effect_guard=guard,deadline_monotonic=deadline)
    X.require_ready()
    public_save(X,'operator-bootstrap-result.json',out)
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--plan',required=True);p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('action',choices=('prepare','install','start','select','watch','bootstrap','stop','cleanup','uninstall'))
    a=p.parse_args();X=Context(a.plan,a.expected_plan_sha256)
    if a.action=='prepare':value=preparation(X)
    elif a.action in ('install','start','stop','uninstall'):value=lifecycle(X,a.action)
    elif a.action=='select':value=select(X)
    elif a.action=='watch':value=watch(X)
    elif a.action=='bootstrap':value=operator(X)
    else:
        value=cleanup_valid(X);public_save(X,'cleanup.json',value)
    print(json.dumps(value,ensure_ascii=False))
    return 0 if value.get('returncode',0)==0 else 3

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:
        print(json.dumps({'status':'PHASE1_UNCONFIRMED','error_type':type(e).__name__,'code':str(e) if type(e).__name__=='Refused' else 'SEE_PRIVATE_DIAGNOSTIC','provider_calls':0}))
        raise SystemExit(3) from None
