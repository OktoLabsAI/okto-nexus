"""New observation namespace; same installed tasks after six confirmed exits."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

HERE=Path(__file__).resolve().parent
RECOVERY=HERE.parent
sys.path.insert(0,str(RECOVERY))
from recovery_context import RecoveryContext,require,read_json,sha,pin,reserve
import recovery_observation as observed
import recovery_connector as connector
import recovery_nexus as nexus


def validate_exit(proof):
    require(proof.get('physical_exit_confirmed') is True and proof.get('force_used') is False,
            'NORMAL_SIX_PROCESS_EXIT_REQUIRED')
    require(set(proof['cohorts'])==set(proof['exits'])=={'nexus','connector'},'BOTH_COHORTS_REQUIRED')
    for component in ('nexus','connector'):
        selected=proof['cohorts'][component]
        require(set(proof['exits'][component])==set(observed.ROLES),'THREE_ROLE_PROOFS_REQUIRED')
        for role in observed.ROLES:
            actual=proof['exits'][component][role];expected=selected['cohort'][role]
            require(actual.get('physical_exit') is True and actual.get('exit_code')==0
                    and actual.get('pid')==expected['pid'] and actual.get('birth')==expected['birth'],
                    'EXACT_NORMAL_PHYSICAL_EXIT_REQUIRED')


def validate_fresh(current,old):
    require(current['generation']!=old['generation'] and current['cohort']['cycle_id']!=old['cohort']['cycle_id'],
            'FRESH_GENERATION_AND_CYCLE_REQUIRED')
    require(current['instance_id']==old['instance_id'] and current['task']['name']==old['task']['name']
            and current['task']['digest']==old['task']['digest'],'INSTALLED_SCOPE_CHANGED')


class Context:
    def __init__(self,path,expected):
        self.restart_plan_path=Path(path).resolve()
        require(self.restart_plan_path==HERE/'plan.json' and sha(path)==expected,'RESTART_PLAN_CHANGED')
        self.restart_plan_sha256=expected;self.restart=read_json(path)
        for item in self.restart['pins'].values():pin(item)
        self.base=RecoveryContext(pin(self.restart['lifecycle']),self.restart['lifecycle']['sha256'])
        self.P,self.C=self.base.P,self.base.C
        self.ROOT,self.python,self.installed=self.base.ROOT,self.base.python,self.base.installed
        self.plan_path,self.plan_sha256=self.base.plan_path,self.base.plan_sha256
        self.CONTROL=HERE;self.PUBLIC=HERE/'public';self.PRIVATE=HERE/'private'
        self.previous=read_json(pin(self.restart['exit_proof']));validate_exit(self.previous)
        self.done=read_json(pin(self.restart['completed']))
        self.binding_basis()

    def binding_basis(self):
        from okto_nexus_connector.platform.paths import state_file
        from okto_nexus_connector.storage.state_store import StateStore
        require(self.done.get('current_credential_epoch')==2 and self.done.get('material_status')=='reuse_existing',
                'CONFIGURED_EPOCH2_REQUIRED')
        profile=Path(self.P['paths']['operator_home'])/'terminal/profiles'/(self.done['profile']+'.json')
        document=read_json(profile)
        import recovery_binding as binding_guards
        binding=read_json(pin(self.restart['binding_plan']))
        draft=read_json(pin(binding['draft']))
        binding_guards.validate_done(document,binding,draft)
        review=read_json(pin(self.done['canonical_review_pin']))
        require(document.get('remote_scope')==self.done['remote_scope']
                and document.get('review_revision')==self.done['profile_review_revision']==review['review_revision']
                and document.get('remote_review')==review['review'], 'IMMUTABLE_DONE_SCOPE_CHANGED')
        self.profile_path=profile
        pin(self.done['rotation_import_result_pin']);pin(self.done['canonical_review_pin'])
        state=StateStore(state_file(Path(self.P['paths']['connector_state']))).load()
        identity=state.identity_for(self.done['server_id'],self.done['remote_scope']['agent_id'])
        require(identity is not None and identity.credential_epoch==2 and identity.revoked is False
                and state.preferences.get('vault.fallback_file.approved') is True,'SAME_APPROVED_IDENTITY_REQUIRED')

    def save(self,name,value):
        require(Path(name).name==name and name.endswith('.json'),'INVALID_PUBLIC_NAME')
        reserve(self.PUBLIC/name,dict(value,lifecycle_plan_sha256=self.plan_sha256,
                                     collector_recovery_plan_sha256=self.restart_plan_sha256))
    def require_tags(self,value):
        self.base.require_tags(value)
        require(value.get('collector_recovery_plan_sha256')==self.restart_plan_sha256,'RESTART_RECEIPT_CHANGED')
    def env(self):return self.base.env()
    def connector_env(self):return self.base.connector_env()
    def require_migrated(self,component):return self.base.require_migrated(component)
    def require_nexus_ready(self):return observed.current_ready(self)
    def require_ready(self):return {'nexus':self.require_nexus_ready(),'connector':connector.current_ready(self)}
    def pre_start(self,component):
        self.binding_basis();self.require_migrated(component)
        require(sha(self.profile_path)==self.restart['profile_ancestry']['sha256'],
                'PROFILE_CHANGED_SINCE_RESTART_SELECTION')
        old=self.previous['cohorts'][component]
        service=observed.installation(self) if component=='nexus' else connector.installation(self)
        _,task=service.observe()
        require(task is not None and task.enabled and not task.active and task.digest==old['task']['digest']
                and self.C['tasks'][component]['name']==old['task']['name'],'SAME_INACTIVE_INSTALLED_TASK_REQUIRED')
        observed.canonical_absence(self,component)
        if component=='nexus':nexus.port_free(self)
        else:self.require_nexus_ready()
        return {'same_installed_task':True,'canonical_absence':True,
                'previous_six_exit_proof_sha256':self.restart['exit_proof']['sha256'],
                'work_settlement_claimed':False}


def argv(context,component,action):
    if component=='connector':return connector.commands(context)[action]
    return next(step['argv'] for step in context.C['steps'] if step['component']=='nexus' and step['action']==action)


def call(context,component,action):
    prefix='' if component=='nexus' else 'connector-'
    if action=='start':basis=context.pre_start(component)
    else:
        basis=(observed.current_ready(context) if component=='nexus' else connector.current_ready(context))
    for directory in (context.PUBLIC,context.PRIVATE):
        if not directory.exists():observed.secure_directory(directory,HERE)
    command=argv(context,component,action)
    require('--force' not in command,'NO_FORCE_SELECTED')
    context.save(prefix+action+'-reserved.json',{'argv':command,'basis':basis,'provider_calls_selected':0,
        'reinstall_selected':False,'force_used':False})
    if action=='start':context.pre_start(component)
    else:
        (observed.current_ready(context) if component=='nexus' else connector.current_ready(context))
    out=context.PRIVATE/(prefix+action+'.stdout');err=context.PRIVATE/(prefix+action+'.stderr')
    with out.open('xb') as stdout,err.open('xb') as stderr:
        child=subprocess.Popen(command,cwd=context.ROOT,
            env=context.connector_env() if component=='connector' else context.env(),
            stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        code=child.wait()  # Retain canonical CLI, no timeout-kill or replay.
    result={'returncode':code,'stdout_sha256':sha(out),'stderr_sha256':sha(err),
            'physical_exit_confirmed':False,'provider_calls_selected':0,'force_used':False}
    try:
        raw=read_json(out);data=raw.get('data',raw)
        result['projection']={k:data.get(k) for k in ('state','reason','code','pid','generation','instance_id','shutdown_outcome') if k in data}
    except (ValueError,TypeError,AttributeError):result['parse_error']='CLI_JSON_UNCONFIRMED'
    context.save(prefix+action+'-returned.json',result)
    require(code==0 and not result.get('parse_error'),'CANONICAL_ACTION_UNCONFIRMED_NO_REPLAY')
    return result


def select(context,component):
    prefix='' if component=='nexus' else 'connector-'
    returned=read_json(context.PUBLIC/(prefix+'start-returned.json'));context.require_tags(returned)
    require(returned.get('returncode')==0 and not returned.get('parse_error'),'START_NOT_CONFIRMED')
    module=observed if component=='nexus' else connector
    current,handles=module.capture(context)
    try:
        validate_fresh(current,context.previous['cohorts'][component])
        context.save(component+'-owner-selection.json',current)
        return current
    finally:
        for handle in handles.values():handle.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('component',choices=('nexus','connector'))
    parser.add_argument('action',choices=('start','select','watch','stop','cleanup'))
    args=parser.parse_args();context=Context(args.plan,args.expected_plan_sha256)
    if args.action in ('start','stop'):result=call(context,args.component,args.action)
    elif args.action=='select':result=select(context,args.component)
    elif args.action=='watch':
        if args.component=='connector':result=connector.watch(context)
        else:
            saved=nexus.public_save
            nexus.public_save=lambda current,name,value:current.save(name,value)
            try:result=nexus.watch(context)
            finally:nexus.public_save=saved
    else:
        result=(nexus if args.component=='nexus' else connector).cleanup_valid(context)
        context.save(args.component+'-cleanup.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
