"""Additive Connector-only view after the real zero-admission SVC20 campaign."""
from pathlib import Path
import importlib.util,sys,sqlite3,time
HERE=Path(__file__).resolve().parent
RECOVERY=HERE.parent
sys.path.insert(0,str(RECOVERY))
from recovery_context import RecoveryContext,require,read_json,sha,pin,reserve
import recovery_connector as connector
import recovery_observation as observed

LIFECYCLE_SHA='8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27'
ROLES=('parent','launcher','child')

def verify_freeze(expected):
    require(sha(HERE/'runtime-freeze.json')==expected,'POST_SVC20_FREEZE_CHANGED')
    value=read_json(HERE/'runtime-freeze.json')
    for item in value['files'].values():pin(item)
    return value

def next_connect_module():
    path=RECOVERY/'svc20-next-connect/next_connect.py'
    spec=importlib.util.spec_from_file_location('post_svc20_next_connect',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def validate_exit(proof,selection,plan_sha):
    require(proof.get('next_connect_plan_sha256')==plan_sha and selection.get('next_connect_plan_sha256')==plan_sha,'SVC20_PROOF_PLAN_CHANGED')
    require(proof.get('force_used') is False and proof.get('cohort')==selection.get('cohort')
        and set(proof.get('exits',{}))==set(ROLES),'SVC20_COHORT_PROOF_INCOMPLETE')
    for role in ROLES:
        v=proof['exits'][role];identity=selection['cohort'][role]
        require(v.get('physical_exit') is True and v.get('pid')==identity['pid'] and v.get('birth')==identity['birth']
            and type(v.get('exit_code')) is int,'SVC20_PHYSICAL_EXIT_REQUIRED')

def current_epoch(database,server_id,agent_id):
    db=sqlite3.connect(Path(database).as_uri()+'?mode=ro',uri=True,timeout=1)
    try:
        db.execute('PRAGMA query_only=ON');end=time.monotonic()+2
        db.set_progress_handler(lambda:int(time.monotonic()>end),1000)
        active=db.execute('SELECT is_active FROM agents WHERE agent_id=?',(agent_id,)).fetchone()
        revision=db.execute('SELECT server_id,credential_epoch FROM execution_agent_revisions WHERE agent_id=?',(agent_id,)).fetchone()
        require(active==(1,) and revision==(server_id,2),'CURRENT_EPOCH2_REQUIRED')
        return 2
    finally:db.close()

def validate_result(result,plan_sha):
    require(result.get('next_connect_plan_sha256')==plan_sha and result.get('status')=='PASS_SCOPED','REAL_SVC20_PASS_REQUIRED')
    for name in ('configured_next_connect','same_binding_grants','both_connector_cohorts_exited',
                 'connector_task_retained_inactive','nexus_same_ready_cohort'):
        require(result.get(name) is True,'SVC20_FACT_UNCONFIRMED_'+name)
    require(type(result.get('new_execution_operations')) is int and result['new_execution_operations']==0
        and result.get('force_used') is False and result.get('productive_start_selected') is False
        and result.get('provider_calls_selected')==0,'SVC20_EFFECT_SCOPE_CHANGED')

def validate_basis(plan,base):
    refs=plan['basis'];values={k:read_json(pin(v)) for k,v in refs.items()}
    source=values['svc20_plan'];ps=refs['svc20_plan']['sha256']
    require(Path(refs['svc20_plan']['path']).resolve()==RECOVERY/'svc20-next-connect/selected-plan.json','SVC20_PLAN_PATH_CHANGED')
    validate_result(values['svc20_result'],ps)
    before=values['before'];first=before['connector']
    require(before.get('next_connect_plan_sha256')==ps,'SVC20_BEFORE_PLAN_CHANGED')
    # The initial selection is nested inside before.json; the containing record supplies its tag.
    validate_exit(values['initial_exit'],dict(first,next_connect_plan_sha256=ps),ps)
    final=values['after_connect'];validate_exit(values['final_exit'],final,ps)
    require(first['task']['digest']==final['task']['digest']==plan['task_digest']
        and first['task']['name']==final['task']['name']==base.C['tasks']['connector']['name']
        and final['instance_id']==base.C['tasks']['connector']['instance_id'],'SVC20_TASK_SCOPE_CHANGED')
    require(before['accounting']['operation_count']==0 and before['accounting']['operation_ids']==[],'SVC20_ZERO_BASELINE_REQUIRED')
    require(source['lifecycle_plan']['sha256']==base.plan_sha256
        and source['completed']==refs['completed'] and source['rotation']==refs['rotation'],'SVC20_COMPLETION_CHAIN_CHANGED')
    migration=values['migration'];base.require_tags(migration)
    require(migration.get('returncode')==0 and migration.get('projection',{}).get('applied') is True
        and migration.get('target_context_sha256')==plan['migrated_context_sha256'],'MIGRATION_BASIS_REQUIRED')
    profile=Path(base.P['paths']['operator_home'])/'terminal/profiles/m1-sonnet-remote-recovery02.json'
    done=values['completed'];require(sha(profile)==done['profile_sha256'],'DONE_PROFILE_CHANGED')
    require(done['rotation_import_result_pin']['sha256']==refs['rotation']['sha256'],'DONE_ROTATION_CHAIN_CHANGED')
    module=next_connect_module();scope=module.validate_completed(source,done,read_json(profile),values['rotation'])
    return values,scope,module

class Context:
    def __init__(self,path,expected_sha256):
        self.post_plan_path=Path(path).resolve();self.post_plan_sha256=expected_sha256
        require(self.post_plan_path==HERE/'selected-plan.json' and sha(path)==expected_sha256,'POST_SVC20_PLAN_CHANGED')
        self.post_plan=read_json(path)
        require(self.post_plan['status']=='ROOT_SELECTED_AFTER_REAL_SVC20_ZERO_ADMISSIONS'
            and self.post_plan['scope']=='ONE_CONNECTOR_START_FRESH_COHORT_NO_REINSTALL','POST_SVC20_SELECTION_REQUIRED')
        verify_freeze(self.post_plan['runtime_freeze_sha256'])
        self.base=RecoveryContext(RECOVERY/'lifecycle-plan.json',LIFECYCLE_SHA)
        self.P,self.C,self.ROOT,self.python,self.installed=self.base.P,self.base.C,self.base.ROOT,self.base.python,self.base.installed
        self.plan_sha256=self.base.plan_sha256
        self.plan_path=self.base.plan_path
        self.CONTROL=HERE;self.PUBLIC=HERE/'public';self.PRIVATE=HERE/'private'
        self.values,self.scope,self.svc20=validate_basis(self.post_plan,self.base)
        require(sha(self.P['source_contexts']['connector']['path'])==self.post_plan['migrated_context_sha256'],'MIGRATED_CONTEXT_CHANGED')

    def save(self,name,value):
        require(Path(name).name==name and name.endswith('.json'),'PUBLIC_NAME_INVALID')
        reserve(self.PUBLIC/name,dict(value,lifecycle_plan_sha256=self.plan_sha256,post_svc20_plan_sha256=self.post_plan_sha256))
    def require_tags(self,value):
        self.base.require_tags(value)
        require(value.get('post_svc20_plan_sha256')==self.post_plan_sha256,'POST_SVC20_RECEIPT_PLAN_CHANGED')
    def env(self):return self.base.env()
    def connector_env(self):return self.base.connector_env()
    def require_migrated(self,component):return self.base.require_migrated(component)
    def require_nexus_ready(self):return self.base.require_nexus_ready()
    def require_ready(self):return {'nexus':self.require_nexus_ready(),'connector':connector.current_ready(self)}
    def require_pre_start(self):
        self.require_nexus_ready();self.base.require_migrated('connector')
        _,task=connector.installation(self).observe()
        require(task is not None and task.enabled and not task.active and task.digest==self.post_plan['task_digest'],'INSTALLED_IDLE_TASK_REQUIRED')
        observed.canonical_absence(self,'connector')
        current_epoch(Path(self.P['paths']['server_home'])/'nexus.db',self.scope['server_id'],self.scope['agent_id'])
        actual=self.svc20.accounting(Path(self.P['paths']['server_home'])/'nexus.db',self.values['svc20_plan'])
        require(actual==self.values['before']['accounting'],'ZERO_ADMISSION_OR_GRANT_BASELINE_CHANGED')
        return {'zero_execution_operations':True,'same_grants':True,'task_digest':task.digest,'canonical_owner_absent':True}
