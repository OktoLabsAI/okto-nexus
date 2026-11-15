"""Paid remote Sonnet context. No effects at import; no inherited Codex budget."""
from pathlib import Path
from concurrent.futures import TimeoutError
import argparse
import importlib.util
import subprocess
import sys
import time

from request_context import require,read_json,pin,sha,reserve
from reused_observation import Process,ROLES,same_cycle,same_owner,secure_directory
from remote_work import atomic

HERE=Path(__file__).resolve().parent
WORK_IDS={'useful':'m1-sonnet-remote-useful-05','continuation':'m1-sonnet-remote-continuation-06'}

class ConsoleFuture:
    """Retain both Windows launcher and runtime, never kill or parallelize CLI."""
    def __init__(self,process,kernel,metadata=None,birth_reader=None):
        self.process=process;self.kernel=kernel;self.metadata=metadata;self.birth_reader=birth_reader
        self.runtime_handle=None;self.runtime_owned=False;self.runtime_exit_proven=False
        self.identity_error=None
    def _bind_runtime(self):
        if self.runtime_handle:return True
        if self.metadata is None or self.birth_reader is None:return False
        try:
            if not self.metadata.is_file():return False
            require(self.metadata.stat().st_size<=4096,'CONSOLE_METADATA_TOO_LARGE')
            value=read_json(self.metadata)
            require(all(type(value.get(k)) is int and value[k]>0 for k in ('pid','parent_pid','birth')),'CONSOLE_METADATA_INVALID')
            require(value['pid']==self.process.pid or value['parent_pid']==self.process.pid,'CONSOLE_RUNTIME_ANCESTRY_UNKNOWN')
            handle=getattr(self.process,'_svc09_runtime_handle',None)
            owned=bool(handle)
            if not handle:
                if value['pid']==self.process.pid:handle=int(self.process._handle)
                else:handle=self.kernel.OpenProcess(0x100000|0x1000,False,value['pid']);owned=bool(handle)
            require(handle,'CONSOLE_RUNTIME_HANDLE_UNKNOWN')
            try:require(self.birth_reader(self.kernel,handle)==value['birth'],'CONSOLE_RUNTIME_IDENTITY_UNKNOWN')
            except BaseException:
                if owned:self.kernel.CloseHandle(handle);self.process._svc09_runtime_handle=None
                raise
            self.runtime_handle=handle;self.runtime_owned=owned
            return True
        except Exception as error:
            self.identity_error=type(error).__name__;return False
    def done(self):
        if self.runtime_exit_proven:return True
        if not self._bind_runtime():return False
        try:self.runtime_exit_proven=self.process.poll() is not None and self.kernel.WaitForSingleObject(self.runtime_handle,0)==0
        except Exception as error:self.identity_error=type(error).__name__;return False
        return self.runtime_exit_proven
    def poll(self):return self.process.returncode if self.done() else None
    def result(self,timeout):
        end=time.monotonic()+timeout
        while not self.done() and time.monotonic()<end:time.sleep(.05)
        if not self.done():raise TimeoutError()
        if self.runtime_handle and self.runtime_owned:self.kernel.CloseHandle(self.runtime_handle)
        self.runtime_handle=None;self.process._svc09_runtime_handle=None
        return {'console_processes_exited':True}

def load_module(name,source):
    path=pin(source);spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

def validate_completed(completed,rotation,profile,plan,review,binding,draft,guards):
    # The original transfer remains failed. Only the separately selected rotation,
    # import and canonical reuse/Finish chain can authorize this new profile.
    guards.require_rotation_before_review(rotation,binding)
    guards.validate_done(profile,binding,draft)
    prerequisites=plan['prerequisites']
    reference=lambda value:{k:value[k] for k in ('path','sha256')}
    require(rotation.get('rotation_plan_sha256')==binding['rotation_plan']['sha256']
        and rotation.get('authorization_receipt_sha256')==prerequisites['rotation_authority']['sha256'],
        'ROTATION_AUTHORITY_CHANGED')
    require(completed.get('binding_plan_sha256')==review.get('binding_plan_sha256')==plan['binding_plan']['sha256']
        and completed.get('lifecycle_plan_sha256')==review.get('lifecycle_plan_sha256')==plan['recovery_plan']['sha256']
        and rotation.get('lifecycle_plan_sha256')==plan['recovery_plan']['sha256'], 'RECOVERY_RECEIPT_CHAIN_CHANGED')
    for value in (completed,review):
        require(type(value.get('current_credential_epoch')) is int and value['current_credential_epoch']==2
            and value.get('rotation_import_result_pin')==reference(prerequisites['rotation_result']), 'ROTATION_IMPORT_PIN_CHANGED')
    require(completed.get('canonical_review_pin')==reference(prerequisites['canonical_review'])
        and completed.get('profile_review_revision')==review.get('review_revision')==profile.get('review_revision')
        and review.get('review')==profile.get('remote_review')
        and review.get('profile')==plan['profile']
        and completed.get('material_status')=='reuse_existing','CANONICAL_REVIEW_CHAIN_CHANGED')
    require(profile.get('state')=='done' and completed.get('profile')==plan['profile']
        and profile.get('server_id')==completed.get('server_id')==plan['server_id']
        and profile.get('remote_scope')==completed.get('remote_scope'),'COMPLETED_REMOTE_SCOPE_CHANGED')
    scope=completed['remote_scope']
    require(scope.get('agent_id')==plan['agent_id'] and scope.get('adapter_id')=='claude_stream'
        and scope.get('candidate_ref')==plan['candidate_ref'],'REVIEWED_CLAUDE_BINDING_CHANGED')
    require(profile.get('selection',{}).get('operator_profile')==plan['operator_profile'],'OPERATOR_PROFILE_CHANGED')
    return scope

def bind_restarted_cohorts(context,restarted):
    require(restarted.restart_plan_sha256==context.P['restart_plan']['sha256']
        and restarted.base.plan_sha256==context.P['recovery_plan']['sha256'],'RESTART_AUTHORITY_CHANGED')
    require(restarted.done['remote_scope']==context.binding_scope,'RESTART_BINDING_CHANGED')
    for component in ('nexus','connector'):
        for suffix,file_suffix in (('selection','owner-selection'),('watch_started','exit-watch-started')):
            source=context.P['prerequisites'][component+'_'+suffix]
            require(Path(source['path']).resolve()==restarted.PUBLIC/(component+'-'+file_suffix+'.json'),
                'FRESH_OBSERVER_NAMESPACE_REQUIRED')
            restarted.require_tags(read_json(pin(source)))
    context.base=restarted;context.transfer=restarted

def check_prior_reservations(private,public,request,ids):
    require(request in ids.values(),'REQUEST_NOT_SELECTED')
    allowed={rid+'-reserved.json' for rid in ids.values()}
    files=list(Path(private).glob('*-reserved.json'))
    model=[p for p in files if p.name in allowed]
    require(len(model)<2 and not (Path(private)/(request+'-reserved.json')).exists(),'WORK_SELECTION_ALREADY_RESERVED')
    for path in model:
        prior=read_json(path);result=Path(public)/(prior['request_id']+'-result.json')
        require(result.exists(),'PREVIOUS_RESERVATION_UNCONFIRMED')
        value=read_json(result)
        require(value.get('terminal_observed') is True and value.get('canonical_succeeded') is True
            and value.get('useful_result_confirmed') is True,'PREVIOUS_WORK_NOT_SUCCESSFUL')

class Context:
    def __init__(self,path,expected):
        path=Path(path).resolve();require(path==HERE/'work-plan.json' and sha(path)==expected,'WORK_PLAN_CHANGED')
        self.P=read_json(path);self.plan_sha256=expected
        from successor_policy import authorize_plan
        authorize_plan(self.P)
        require(self.P['scope']=='TWO_REMOTE_SONNET_WORK_CALLS_NO_SETUP_REPLAY'
            and self.P['request_ids']==WORK_IDS and self.P['model']=='sonnet'
            and self.P['budget']=={'limit':500000,'preventive':480000,'initial_reserve':50000,'next_input_multiplier':2,'next_output_margin':32000}
            and self.P['root_retains_observers'] is True,'WORK_SCOPE_CHANGED')
        recovery=read_json(pin(self.P['recovery_plan']))
        for value in recovery['runtime_pins'].values():pin(value)
        self.recovery_module=load_module('recovery_context',recovery['runtime_pins']['recovery_context.py'])
        self.nexus=load_module('recovery_observation',recovery['runtime_pins']['recovery_observation.py'])
        self.connector=load_module('recovery_connector',recovery['runtime_pins']['recovery_connector.py'])
        self.base=self.recovery_module.RecoveryContext(pin(self.P['recovery_plan']),self.P['recovery_plan']['sha256'])
        self.transfer=self.base
        self.ROOT=self.base.ROOT;self.PUBLIC=HERE/'paid-work/public';self.PRIVATE=HERE/'paid-work/private'
        self.request_ids=dict(WORK_IDS);self.prompts=dict(self.P['prompts']);self.handles={};self.children=[];self._flow=None
        self.selected={};self._last_request=None;self._defer_decision=False
        manifest=read_json(pin(self.P['work_runtime_freeze']))
        for value in manifest['files'].values():pin(value)
        for value in manifest['dependencies'].values():pin(value)
        for name,value in self.P['runtime_pins'].items():
            require(Path(value['path']).resolve()==HERE/name,'CONTEXT_RUNTIME_PATH_CHANGED');pin(value)
        for value in self.P['prerequisites'].values():pin(value)
        binding=read_json(pin(self.P['binding_plan']))
        for value in binding['pins'].values():pin(value)
        require(binding['lifecycle_plan']==self.P['recovery_plan'],'BINDING_LIFECYCLE_CHANGED')
        require(self.P['prerequisites']['original_failed_transfer']==binding['pins']['old_failed_transfer']
            and read_json(pin(binding['pins']['old_failed_transfer'])).get('status')=='UNCONFIRMED',
            'ORIGINAL_FAILED_TRANSFER_NOT_PRESERVED')
        load_module('recovery_onboarding',binding['pins']['draft_guard'])
        guards=load_module('sonnet_paid_recovery_binding',binding['pins']['entry'])
        rotation_plan=read_json(pin(binding['rotation_plan']))
        require(Path(rotation_plan['authorization_receipt']).resolve()==Path(self.P['prerequisites']['rotation_authority']['path']).resolve(),'ROTATION_AUTHORITY_PATH_CHANGED')
        self.profile_path=Path(self.base.P['paths']['operator_home'])/'terminal/profiles'/(self.P['profile']+'.json')
        completed=read_json(pin(self.P['prerequisites']['completed_profile']))
        self.binding_scope=validate_completed(completed,read_json(pin(self.P['prerequisites']['rotation_result'])),
            read_json(self.profile_path),self.P,read_json(pin(self.P['prerequisites']['canonical_review'])),binding,
            read_json(pin(binding['draft'])),guards)
        restart=load_module('sonnet_successor_lifecycle',self.P['restart_context_source'])
        restarted=restart.Context(pin(self.P['restart_plan']),self.P['restart_plan']['sha256'])
        bind_restarted_cohorts(self,restarted)
        self.expected_scope={k:self.binding_scope[k] for k in ('server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id')}
        require(Path(self.P['project']).resolve()==Path(self.base.P['paths']['connector_project']).resolve(),'PROJECT_CHANGED')
        require(Path(self.P['report']).resolve()==(self.ROOT/'campaign/deliverables/remote/report.json').resolve(),'REPORT_PATH_CHANGED')
        pin(self.P['input_fixture']);pin(self.P['rtk']);pin(self.P['python_executable']);pin(self.P['console_helper'])
        # Only installed package/provenance plus campaign code; never repository imports.
        require(Path(sys.executable).resolve()==Path(self.base.python).resolve(),'WORK_PYTHON_CHANGED')
        self._cli_source=manifest['dependencies']['cli_flow.py']
        self._scope_source=manifest['dependencies']['token_collector.py']

    def validate_budget(self,budget):
        from successor_policy import validate_history
        validate_history(budget,read_json(pin(self.P['budget_seed'])))

    def prepare(self):
        require(not self.PUBLIC.exists() and not self.PRIVATE.exists(),'WORK_NAMESPACE_ALREADY_PREPARED')
        from sonnet_usage import restore_budget
        seed=read_json(pin(self.P['budget_seed']))
        self.validate_budget(restore_budget(seed))
        ancestor=pin(self.P['predecessor_work_checkpoint'])
        self.PUBLIC.mkdir(parents=True);secure_directory(self.PRIVATE,HERE)
        reserve(self.PRIVATE/'sonnet-budget.json',seed)
        with (self.PRIVATE/'predecessor-work-checkpoint.json').open('xb') as stream:
            stream.write(ancestor.read_bytes())
        reserve(self.PUBLIC/'preparation.json',{'plan_sha256':self.plan_sha256,'provider_calls':0,'state':'PREPARED',
            'carried_observed_tokens':144004,'carried_reservations':2,'preventive':480000,'limit':500000,
            'budget_seed_sha256':self.P['budget_seed']['sha256'],
            'predecessor_checkpoint_sha256':self.P['predecessor_work_checkpoint']['sha256']})
        return {'state':'PREPARED','provider_calls':0}

    def activate(self,phase):
        require(phase in WORK_IDS,'WORK_PHASE_INVALID')
        require(read_json(self.PUBLIC/'preparation.json')['plan_sha256']==self.plan_sha256,'WORK_PREPARATION_CHANGED')
        self._last_request=WORK_IDS[phase]
        if phase=='useful':require(not Path(self.P['report']).exists(),'NEW_REPORT_REQUIRED')
        pin(self.P['input_fixture'])
        try:
            for component,capture_fn,ctx in (('nexus',self.nexus.capture,self.base),('connector',self.connector.capture,self.transfer)):
                expected=read_json(pin(self.P['prerequisites'][component+'_selection']))
                selected,handles=capture_fn(ctx)
                self.handles[component]=handles
                same_cycle(expected['cohort'],selected['cohort']);same_owner(expected,selected)
                self.selected[component]=selected
            self._external_watchers()
            self.require_ready()
        except BaseException:
            self.close();raise

    def _external_watchers(self):
        proofs={}
        for component in ('nexus','connector'):
            context=self.base if component=='nexus' else self.transfer
            exited=context.PUBLIC/(component+'-exit-proof.json')
            if exited.exists():
                proof=read_json(exited);chosen=self.selected[component]['cohort']
                context.require_tags(proof)
                require(proof.get('cohort')==chosen and proof.get('force_used') is False
                    and set(proof.get('exits',{}))==set(ROLES),'EXTERNAL_EXIT_PROOF_CHANGED')
                require(all(proof['exits'][r].get('physical_exit') is True and proof['exits'][r].get('pid')==chosen[r]['pid']
                    and proof['exits'][r].get('birth')==chosen[r]['birth'] for r in ROLES),'EXTERNAL_PHYSICAL_EXIT_UNCONFIRMED')
                proofs[component]={'physical_exit_confirmed':True,'proof_sha256':sha(exited)}
                continue
            started=read_json(pin(self.P['prerequisites'][component+'_watch_started']))
            context.require_tags(started)
            require(started['cohort']==self.selected[component]['cohort'] and started['retained_roles']==list(ROLES),'EXTERNAL_WATCH_SCOPE_CHANGED')
            observed=Process(started['observer']['pid'])
            try:require(observed.birth==started['observer']['birth'] and not observed.exited(),'EXTERNAL_WATCH_NOT_LIVE')
            finally:observed.close()
            proofs[component]={'observer':started['observer'],'cohort':started['cohort']}
        return proofs

    def require_ready(self):
        require(set(self.handles)=={'nexus','connector'} and not any(h.exited() for group in self.handles.values() for h in group.values()),'OWN_COHORT_NOT_LIVE')
        nexus=self.base.require_nexus_ready();connector=self.connector.current_ready(self.transfer)
        for name,value in (('nexus',nexus),('connector',connector)):
            same_owner(self.selected[name],value);same_cycle(self.selected[name]['cohort'],value['cohort'])
        return {'nexus':nexus,'connector':connector}

    def _control_identity(self,component,*,query_required=True):
        chosen=self.selected[component]
        require(not any(h.exited() for h in self.handles[component].values()),'CONTROL_COHORT_NOT_LIVE')
        if component=='nexus':
            from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
            home=Path(self.base.P['paths']['server_home'])
            raw=inspect_local_server(home=home,database=home/'nexus.db',host='127.0.0.1',port=58631,timeout=5)
            if query_required:require(raw.get('ready_for_queries') is True and raw.get('state') in ('ready','stopping'),'NEXUS_CONTROL_UNAVAILABLE')
        else:
            from okto_nexus_connector.daemon import manager
            raw=manager.status(Path(self.base.P['paths']['connector_state']),timeout=5).to_json()
            if query_required:require(raw.get('running') is True and raw.get('ipc_ok') is True and raw.get('state') in ('ready','stopping'),'CONNECTOR_CONTROL_UNAVAILABLE')
        require(all(raw.get(k)==chosen.get(k) for k in ('pid','generation','instance_id')),'CONTROL_OWNER_CHANGED')
        return chosen

    def owner_observation(self):
        for component in ('nexus','connector'):self._control_identity(component)
        own=self.selected['connector'];admission=self.PRIVATE/(self._last_request+'-admission.json')
        operation=read_json(admission)['operation_id'] if admission.exists() else None
        return {'identity_matches':True,'operation_id':operation,
            'identity':{'pid':own['pid'],'birth':own['cohort']['child']['birth'],'generation':own['generation']}}

    def work_flow(self):
        if self._flow is None:
            load_module('token_collector',self._scope_source)
            cls=load_module('sonnet_paid_cli_flow',self._cli_source).CLIFlow
            from okto_nexus.adapters.inbound.cli.terminal_target import RemoteTarget
            home=Path(self.base.P['paths']['operator_home'])
            flow=cls(RemoteTarget(home,self.P['operator_profile']),self.P['profile'],['--home',str(home)],operator_profile=self.P['operator_profile'])
            session=flow.document.get('session_id')
            if self._last_request==WORK_IDS['useful']:
                checkpoint=home/'terminal/work'/(self.P['profile']+'.json')
                require(sha(checkpoint)==self.P['predecessor_work_checkpoint']['sha256']
                    and sha(self.PRIVATE/'predecessor-work-checkpoint.json')==self.P['predecessor_work_checkpoint']['sha256'],
                    'PREDECESSOR_WORK_CHECKPOINT_CHANGED')
                require(session==self.P['predecessor_session_id']
                    and flow.document.get('scope')==self.expected_scope,'PREDECESSOR_WORK_SCOPE_CHANGED')
                require(flow.document.get('work',{}).get('state') not in ('resolve_submitted','resolved','submit_submitted'),
                    'PREDECESSOR_INTENT_UNCONFIRMED')
                # The installed CLI receives --new-session. Its factory guard still expects
                # the retained old session until TerminalWork resolves and saves the new one.
            else:
                prior=read_json(self.PUBLIC/(WORK_IDS['useful']+'-result.json'))
                require(session==prior['session_id'],'CONTINUATION_PROFILE_SESSION_CHANGED')
            flow.expect(self.expected_scope,'operator',session=session);self._flow=flow
        return self._flow

    def operator_flow(self):return self.work_flow()

    def require_prior_reservations_closed(self,request):check_prior_reservations(self.PRIVATE,self.PUBLIC,request,self.request_ids)

    def publish(self,summary):
        atomic(self.PUBLIC/'live-accounting.json',{'plan_sha256':self.plan_sha256,'request_id':self._last_request,**summary})

    def publish_pending(self,items,session):
        from okto_nexus.application.terminal_connection import document_revision
        result=[]
        for item in items:
            proposal=item.get('request_payload',{}).get('kwargs',{});key=proposal.get('approval_key',{})
            require(all(key.get(k)==self.expected_scope[k] for k in ('server_id','executor_id','binding_id','agent_id','workspace_id'))
                and key.get('session_id')==session,'PENDING_SCOPE_CHANGED')
            require(proposal.get('recipient_agent_id','operator')=='operator','QUESTION_NOT_FOR_OPERATOR')
            # Exact native question is retained only in the ACL-protected namespace;
            # public status carries bounded IDs/revision, no command or credentials.
            private={'approval_id':item['approval_id'],'review_revision':document_revision(proposal),'proposal':proposal}
            atomic(self.PRIVATE/'pending-native-request.json',private)
            result.append({k:private[k] for k in ('approval_id','review_revision')})
        atomic(self.PUBLIC/'pending-native-request.json',{'plan_sha256':self.plan_sha256,'session_id':session,'items':result})
        if result:
            self._defer_decision=False
            if not (self.PUBLIC/'svc09-selection.json').exists():
                self._console_hook(session)
                self._defer_decision=True  # Root observes dashboard closure before selecting an answer.

    def _console_observation(self,operation):
        for component,read_cycle,ctx in (('nexus',self.nexus.cycle,self.base),('connector',self.connector.cycle,self.transfer)):
            require(not any(h.exited() for h in self.handles[component].values()),'CONSOLE_COHORT_EXITED')
            same_cycle(self.selected[component]['cohort'],read_cycle(ctx))
        value=self.work_flow().operation(operation,self.expected_scope)
        require(value['operation_id']==operation,'CONSOLE_OPERATION_CHANGED')
        return {k:value.get(k) for k in ('operation_id','scope','executor_stage','admission_state')}

    def _console_hook(self,session):
        from activecontrol import PendingWorker
        start=time.monotonic();flow=self.work_flow();timeout=flow.timeout;flow.set_timeout(2)
        admission=read_json(self.PRIVATE/(self._last_request+'-admission.json'));operation=admission['operation_id']
        try:
            before=self._console_observation(operation)
            reserve(self.PUBLIC/'svc09-selection.json',{'operation_id':operation,'session_id':session,'single_console':True,'new_model_requests':0})
            if before['executor_stage'] in ('SUCCEEDED','FAILED','CANCELLED') or before['admission_state']=='RESOLVED_TERMINAL':
                atomic(self.PUBLIC/'svc09-console-summary.json',{'state':'INCONCLUSIVE_NOT_ACTIVE','before':before});return
            ledger=read_json(self.PRIVATE/'sonnet-budget.json')['state']['sessions']
            current=[item for item in ledger if item['active']==operation and item['scope']['session_id']==session]
            require(len(current)==1,'CONSOLE_ACCOUNTING_SCOPE_UNCONFIRMED')
            helper=load_module('sonnet_selected_console_watch',self.P['console_helper'])
            checkpoint=Path(self.base.P['paths']['operator_home'])/'terminal/work'/(self.P['profile']+'.json')
            from okto_nexus.adapters.inbound.cli import work
            selection={'selected':True,'watch_seconds':5,'python':sys.executable,'profile':self.P['profile'],
                'operator_profile':self.P['operator_profile'],'project':self.P['project'],'home':self.base.P['paths']['operator_home'],
                'session_id':session,'operation_id':operation,'stream_epoch':current[0]['scope']['stream_epoch'],
                'checkpoint_path':str(checkpoint),'checkpoint_sha256':sha(checkpoint),'output':str(self.PUBLIC/'svc09-console'),
                'installed_work_path':work.__file__,'installed_work_sha256':sha(work.__file__),
                'pins':[self.P['console_helper'],self.P['python_executable'],{'path':work.__file__,'sha256':sha(work.__file__)}],
                'environment':{k:v for k in helper.ENV_KEYS for original,v in self.base.env().items() if original.upper()==k.upper()}}
            selection_path=self.PRIVATE/'svc09-console-selection.json';reserve(selection_path,selection)
            kernel=helper.api()[0]  # Resolve fallible API setup before any child exists.
            retained=[]
            def retain_console(process):retained.append(process);self.children.append(process)
            def pending_console(process):
                future=ConsoleFuture(process,kernel,Path(selection['output'])/'console-before.json',helper.birth)
                self.children.append(future)
                return future
            try:
                value,pending=helper.run(selection_path,retain_process=retain_console,wait_seconds=min(8,max(.01,15-(time.monotonic()-start))))
            except BaseException as error:
                if not retained:raise
                future=pending_console(retained[-1])
                try:atomic(self.PUBLIC/'svc09-console-failure.json',{'error_type':type(error).__name__,
                    'launcher_pid':future.process.pid,'runtime_exit_not_inferred':True,'profile_reentry_blocked':True})
                except OSError:pass  # Failed evidence IO must not bypass PendingWorker.
                raise PendingWorker(future) from None
            if pending is None and retained and value.get('runtime_physical_exit_confirmed') is not True:
                # Even a terminated launcher cannot prove its runtime exited.
                raise PendingWorker(pending_console(retained[-1]))
            if pending is not None:
                future=pending_console(pending)
                try:future.result(timeout=max(.01,17-(time.monotonic()-start)))
                except TimeoutError:raise PendingWorker(future) from None
            after=self._console_observation(operation)
            active=before['scope']==after['scope'] and after['executor_stage'] not in ('SUCCEEDED','FAILED','CANCELLED') and after['admission_state']!='RESOLVED_TERMINAL'
            atomic(self.PUBLIC/'svc09-console-summary.json',{'console':value,'before':before,'after':after,
                'same_operation_and_cohorts_active':active,'dashboard_closed_not_inferred':True,'elapsed_seconds':time.monotonic()-start,
                'svc09_acceptance':False,'new_model_requests':0})
        finally:flow.set_timeout(timeout)

    def selected_decision(self):
        if self._defer_decision:return None
        path=self.PRIVATE/'native-decision.json'
        if not path.exists():return None
        require(path.stat().st_size<=4096,'DECISION_FILE_TOO_LARGE')
        value=read_json(path)
        require(set(value)=={'approval_id','decision','review_revision'},'DECISION_FIELDS_CHANGED')
        require(all(isinstance(v,str) and 0<len(v)<=256 for v in value.values()),'DECISION_VALUE_INVALID')
        return value

    def verify_useful(self):
        import csv
        source=pin(self.P['input_fixture']);target=Path(self.P['report'])
        if not target.is_file() or target.stat().st_size>8192:return False
        values=[int(row['value']) for row in csv.DictReader(source.read_text(encoding='utf-8').splitlines())]
        expected={'row_count':len(values),'sum':sum(values),'input_sha256':sha(source)}
        return read_json(target)==expected

    def normal_stop(self):
        for component in ('connector','nexus'):
            if all(h.exited() for h in self.handles[component].values()):continue
            self._control_identity(component,query_required=False)
            selected=self.PUBLIC/(component+'-normal-stop-reserved.json')
            if selected.exists():continue
            argv=self.P['normal_stop_argv'][component]
            require('--force' not in argv and '--timeout' in argv and argv[argv.index('--timeout')+1]=='45','NORMAL_STOP_SCOPE_CHANGED')
            reserve(selected,{'plan_sha256':self.plan_sha256,'cohort':self.selected[component]['cohort'],'force_used':False})
            with (self.PRIVATE/(component+'-stop.stdout')).open('xb') as out,(self.PRIVATE/(component+'-stop.stderr')).open('xb') as err:
                child=subprocess.Popen(argv,cwd=self.ROOT,env=self.transfer.connector_env() if component=='connector' else self.base.env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                self.children.append(child)
                try:rc=child.wait(timeout=180)
                except subprocess.TimeoutExpired:return {'physical_exit_confirmed':False,'pending_cli':True}
            reserve(self.PUBLIC/(component+'-normal-stop-returned.json'),{'returncode':rc,'force_used':False,'stdout_sha256':sha(self.PRIVATE/(component+'-stop.stdout'))})
        end=time.monotonic()+180
        while time.monotonic()<end:
            if self._all_exited():return self._exit_proof()
            time.sleep(.2)
        return {'physical_exit_confirmed':False}

    def _all_exited(self):return bool(self.handles) and all(h.exited() for group in self.handles.values() for h in group.values())

    def _exit_proof(self):
        value={'physical_exit_confirmed':True,'force_used':False,'work_settlement_claimed':False,'cohorts':self.selected,
            'exits':{name:{role:{'pid':h.pid,'birth':h.birth,'physical_exit':True,'exit_code':h.exit_code()} for role,h in group.items()} for name,group in self.handles.items()}}
        atomic(self.PUBLIC/'paid-work-exit-proof.json',value);return value

    def handoff(self,future,summary):
        # Never start another control while a CLI/HTTP worker may still effect.
        pending=bool(future is not None and not future.done()) or any(c.poll() is None for c in self.children)
        value={'plan_sha256':self.plan_sha256,'request_id':self._last_request,'state':'ROOT_CONTAINMENT_REQUIRED',
            'worker_pending':pending,'cohorts':self.selected,'accounting_unknown':True,'new_admissions_closed':True}
        atomic(self.PUBLIC/'handoff-required.json',value)
        if self._all_exited():return {'retained':True,'basis':'EXACT_PHYSICAL_EXIT','proof':self._exit_proof()}
        if future is not None and not future.done():
            try:future.result(timeout=30)
            except TimeoutError:pass
            except Exception:pass
        # These independently running observers were selected by Root before the
        # paid call and retain all six handles. This is NOT provider settlement.
        observers=self._external_watchers()
        value.update(retained=True,basis='ROOT_SELECTED_EXTERNAL_COHORT_OBSERVERS',observers=observers,
            worker_future_still_owned_by_runner=future is not None,provider_settlement_confirmed=False)
        atomic(self.PUBLIC/'handoff-required.json',value);return value

    def close(self):
        def report(value):
            try:atomic(self.PUBLIC/'console-retained-observation.json',value)
            except OSError:pass  # Evidence failure must not release an observed child.
        for child in self.children:
            if not isinstance(child,ConsoleFuture):continue
            if not child.done():
                report({'state':'OBSERVING_RUNTIME_EXIT',
                    'launcher_pid':child.process.pid,'bound_seconds':7200,'new_control_selected':False})
                try:child.result(timeout=7200)
                except TimeoutError:
                    report({'state':'RUNTIME_EXIT_UNKNOWN',
                        'launcher_pid':child.process.pid,'bound_seconds':7200,'new_control_selected':False})
                    continue
            else:child.result(timeout=0)
            report({'state':'EXACT_CONSOLE_PROCESSES_EXITED',
                'launcher_pid':child.process.pid,'new_control_selected':False})
        for group in self.handles.values():
            for handle in group.values():handle.close()
        self.handles={}

def load():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('action',choices=('prepare','useful','continuation'));args=parser.parse_args()
    return Context(args.plan,args.expected_plan_sha256),args.action
