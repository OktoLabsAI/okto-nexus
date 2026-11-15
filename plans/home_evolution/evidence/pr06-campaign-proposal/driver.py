"""Finite HOME-033 driver. No effects at import; no inherited campaign controller.
All installed product imports and I/O are behind exact plan/consent/package checks.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import subprocess
import sys
import time
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage import owned, journal_snapshot, require

ROLES = ('parent', 'launcher', 'child')
PROFILE = 'home-r1-local'
USEFUL_ID = 'home-r1-local-useful-02'
POLICY = {'max_calls': 2, 'observed_limit': 200000, 'preventive': 150000, 'reserve': 50000}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 4 * 1048576, 'DOCUMENT_LIMIT')
    return json.loads(raw)


def publish(path, value):
    """Never overwrite; partial writes remain forensic .writing, never final receipts."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), 'ALREADY_SELECTED')
    temporary = path.with_suffix(path.suffix + '.writing')
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    # Windows rename refuses an existing destination. No replace/cleanup on failure.
    temporary.rename(path)


def consent_valid(plan, document, candidate_sha):
    require(document.get('candidate_sha256') == candidate_sha and
            document.get('user_authorized_paid_campaign') is True and
            isinstance(document.get('user_response_reference'), str) and document['user_response_reference'] and
            document.get('campaign_id') == plan['campaign_id'] and
            document.get('campaign_root') == plan['campaign_root'] and
            document.get('policy') == POLICY and
            document.get('acknowledges_delayed_usage_overshoot') is True, 'NEW_PAID_CONSENT_REQUIRED')


def available_grant(review, binding, now):
    require(review.get('state') == 'authorization_review' and review.get('can_issue') is False,
            'CURRENT_GRANT_REQUIRED')
    require(all(review['scope'].get(k) == binding[k] for k in
                ('server_id','executor_id','binding_id','workspace_id','agent_id','workspace_binding_id','endpoint_id')), 'GRANT_SCOPE_CHANGED')
    for grant in review.get('current_grants', []):
        expiry = grant.get('expires_at')
        if (grant.get('state') == 'available' and {'open','send','interrupt','close'} <= set(grant.get('actions', []))
                and (expiry is None or datetime.fromisoformat(expiry.replace('Z','+00:00')) > now+timedelta(seconds=600))
                and (grant.get('max_executions') is None or grant['used_executions'] + 4 <= grant['max_executions'])):
            return {k: grant.get(k) for k in ('grant_id','revision','expires_at','max_executions','used_executions')}
    raise ValueError('CURRENT_GRANT_REQUIRED')


def contained_admission(kind):
    """All failures AFTER reserving an admission enter the same finite containment."""
    def decorate(function):
        def call(self,*args,**kwargs):
            try:
                return function(self,*args,**kwargs)
            except BaseException as error:
                reserved=self.private/('call-'+kind+'-reserved.json')
                if reserved.exists():
                    fault=self.public/('paid-'+kind+'-fault.json')
                    if not fault.exists():
                        self.save(fault.name,{'error_type':type(error).__name__,
                            'reservation_sha256':sha(reserved),'admissions_closed':True,'retry_allowed':False})
                    marker=self.private/('paid-'+kind+'-containment-selected.json')
                    if not marker.exists():
                        publish(marker,{'plan_sha256':self.plan_sha,'selected_at':time.time(),
                                        'after_reserved_effect_uncertainty':True})
                        try:
                            if not (self.public/'uninstalled.json').exists():self.cleanup()
                        except BaseException as cleanup_error:
                            self.save('paid-'+kind+'-containment-unconfirmed.json',{
                                'error_type':type(cleanup_error).__name__,'root_containment_required':True,
                                'physical_exit_not_asserted':True,'new_admissions_allowed':False,
                                'original_reservation_preserved':True})
                raise
        return call
    return decorate


class Driver:
    def __init__(self, plan_path, expected_sha, *, authorization=None, authorization_sha=None, tests=False):
        require(sha(plan_path) == expected_sha, 'PLAN_CHANGED')
        self.plan_path, self.plan_sha, self.p = Path(plan_path), expected_sha, read(plan_path)
        require(self.p['policy'] == POLICY, 'POLICY_CHANGED')
        require(authorization is not None and authorization_sha is not None,'NEW_PAID_CONSENT_REQUIRED')
        require(sha(authorization)==authorization_sha,'CONSENT_CHANGED')
        consent_valid(self.p,read(authorization),expected_sha)
        self.authorization_sha=authorization_sha
        self.root = Path(self.p['campaign_root']).absolute()
        require(self.root.name.startswith('home-r1-local-codex-'), 'NEW_OWN_NAMESPACE_REQUIRED')
        self.home = owned(self.root, self.root/'nexus-home')
        self.public, self.private = self.root/'public', self.root/'private'
        require(self.p.get('technical_ready') is True, 'TECHNICAL_SELECTION_REQUIRED')
        # No credential, home runtime, service, provider or product import precedes these gates.
        if not tests:
            require(Path(sys.executable).resolve() == Path(self.p['python']['path']).resolve() and
                    sha(sys.executable) == self.p['python']['sha256'], 'INSTALLED_PYTHON_CHANGED')
            for pin in self.p['pins']:
                require(sha(pin['path']) == pin['sha256'], 'PIN_CHANGED')
            require(self.p['package']['installed_payloads_verified'] is True and
                    len(self.p['package']['payload_pins']) > 100, 'INSTALLED_PAYLOAD_PROOF_REQUIRED')
            prefix = Path(sys.prefix).resolve()
            for pin in self.p['package']['payload_pins']:
                target = Path(pin['path']).resolve()
                require(target.is_relative_to(prefix) and sha(target) == pin['sha256'], 'PAYLOAD_CHANGED')
        self.common = ['--home',str(self.home),'--host','127.0.0.1','--port',str(self.p['port']),
                       '--harness-root',self.p['codex_root']]
        self.work_args = ['--profile',PROFILE,'--project',str(self.root/'workspace'),
                          '--readiness-timeout','5','--json',*self.common]

    def save(self, name, value):
        publish(self.public/name, {'campaign_id':self.p['campaign_id'],'plan_sha256':self.plan_sha,
                                  'observed_at':time.time(),'authorization_sha256':getattr(self,'authorization_sha',None), **value})

    def product(self):
        from okto_nexus.adapters.inbound.cli.service import resolve_local_service
        return resolve_local_service(self.common)

    def flow(self):
        from okto_nexus.adapters.inbound.cli.work import open_work
        flow=open_work(self.product(), PROFILE)
        flow.call.timeout=5
        return flow

    def get(self, path):
        require(path.startswith('/api/v1/'), 'CANONICAL_GET_REQUIRED')
        from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
        return LocalOperatorHTTP(host='127.0.0.1', port=self.p['port'], timeout=5,
                                 max_response_bytes=8*1048576)('GET',path)

    def status(self, *, ready=False):
        status = self.product().inspect(timeout=5)
        from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
        install = ServerInstallation(self.home,self.home/'nexus.db')
        require(status.get('instance_id') == install.instance_id, 'INSTANCE_CHANGED')
        if ready:
            require(status.get('state') == 'ready' and status.get('ready_for_queries') is True, 'OWNER_NOT_READY')
        return {k:status.get(k) for k in ('state','reason','instance_id','pid','generation','ready_for_queries')}

    def cycle(self):
        from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
        from okto_nexus.adapters.outbound.service_manager.supervision import read_record
        install = ServerInstallation(self.home,self.home/'nexus.db')
        value = read_record(self.home,install.receipt(),install.instance_id)
        require(isinstance(value,dict), 'SUPERVISOR_RECORD_REQUIRED')
        result={k:value.get(k) for k in ('cycle_id','phase','attempts_started','child_acknowledged')}
        for role in ROLES:
            identity=value.get(role,{})
            require(all(type(identity.get(k)) is int and identity[k]>0 for k in ('pid','birth')),
                    'SUPERVISOR_IDENTITY_REQUIRED')
            result[role]={k:identity[k] for k in ('pid','birth')}
        return result

    def capture(self):
        from own_process import Process
        before, cycle = self.status(), self.cycle()
        require(before['state'] in ('ready','stopping') and cycle['child_acknowledged'] is True and
                before['pid']==cycle['child']['pid'], 'CANONICAL_OWNER_REQUIRED')
        handles={}
        try:
            for role in ROLES:
                h=Process(cycle[role]['pid']); handles[role]=h
                require(h.birth==cycle[role]['birth'] and h.image in self.p['python_images'] and
                        sha(h.image)==self.p['python_images'][h.image], 'PROCESS_BIRTH_OR_IMAGE_CHANGED')
            after=self.status()
            require(all(before[k]==after[k] for k in ('instance_id','pid','generation')) and self.cycle()==cycle,
                    'COHORT_CHANGED')
            return {'owner':before,'cohort':cycle},handles
        except BaseException:
            for h in handles.values(): h.close()
            raise

    def watched(self):
        from own_process import Process
        selected=read(self.public/'watch-started.json')
        require(selected['plan_sha256']==self.plan_sha and not (self.public/'exit-proof.json').exists()
                and not (self.public/'watch-timeout.json').exists(), 'LIVE_WATCH_REQUIRED')
        h=Process(selected['observer']['pid'])
        try:
            require(h.birth==selected['observer']['birth'] and h.image in self.p['python_images'] and
                    sha(h.image)==self.p['python_images'][h.image], 'OBSERVER_CHANGED')
        finally: h.close()
        now=self.status(ready=True)
        require(all(now[k]==selected['owner'][k] for k in ('instance_id','pid','generation')) and
                self.cycle()==selected['cohort'], 'WATCHED_OWNER_CHANGED')
        return selected

    def watch(self):
        from own_process import Process
        selected,handles=self.capture()
        own=Process(os.getpid())
        try:
            self.save('watch-started.json',{**selected,'observer':{'pid':own.pid,'birth':own.birth},
                      'retained_roles':list(ROLES),'terminate_right':False})
            deadline=time.monotonic()+1800
            while not all(h.exited() for h in handles.values()):
                if time.monotonic()>=deadline:
                    self.save('watch-timeout.json',{'physical_exit_confirmed':False})
                    raise ValueError('WATCH_TIMED_OUT_NO_EXIT_PROOF')
                time.sleep(.2)
            self.save('exit-proof.json',{**selected,'physical_exit_confirmed':True,
                'processes':{r:{'pid':h.pid,'birth':h.birth,'exit_code':h.exit_code()} for r,h in handles.items()},
                'work_settlement':'NOT_ASSERTED'})
        finally:
            own.close()
            for h in handles.values():h.close()

    def cli(self, label, argv, *, monitor=None):
        """One subprocess, one selection; raw output only in own private files. Never replay."""
        full=[sys.executable,'-I','-B','-X','utf8','-m','okto_nexus.adapters.inbound.cli.main',*argv]
        publish(self.private/(label+'-reserved.json'),{'plan_sha256':self.plan_sha,
            'argv_sha256':hashlib.sha256(json.dumps(full).encode()).hexdigest(),'selected_at':time.time()})
        env=dict(os.environ); env.pop('PYTHONPATH',None); env['PYTHONDONTWRITEBYTECODE']='1'
        env['OKTO_NEXUS_EMBEDDING_MODE']='off'
        with (self.private/(label+'.stdout')).open('xb') as out, (self.private/(label+'.stderr')).open('xb') as err:
            child=subprocess.Popen(full,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env)
            # Installed action timeouts are not an OS process-termination guarantee.
            # Keep this owning process alive and monitor; never detach a paid admission.
            started=time.monotonic(); monitor_error=None
            while child.poll() is None:
                try:
                    if monitor: monitor()
                except BaseException as error:
                    monitor_error=type(error).__name__
                    # Stop the canonical owned service first; no detached native work.
                    try: self.cleanup()
                    except BaseException: pass  # Preserve unknown; independent watcher remains authoritative.
                    try: child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        child.terminate()  # Only this transient CLI observer, never a runtime/service PID.
                        child.wait(timeout=10)
                    break
                if time.monotonic()-started > (900 if monitor else 180):
                    monitor_error='CLI_WRAPPER_TIMEOUT'
                    child.terminate(); child.wait(timeout=10)
                    break
                time.sleep(.2)
            code=child.wait()
            if monitor_error:
                self.save(label+'-wrapper-error.json',{'error_type':monitor_error,'own_cli_exit':code,
                    'original_selection_retained':True,'native_outcome':'NOT_INFERRED'})
                raise ValueError('CLI_OUTCOME_UNKNOWN_NO_REPLAY')
        output=self.private/(label+'.stdout')
        require(output.stat().st_size<=8*1048576,'CLI_OUTPUT_LIMIT')
        raw=output.read_bytes()
        try:
            value=json.loads(raw)
            require(isinstance(value,dict),'CLI_JSON_REQUIRED')
        except (ValueError,TypeError):
            self.save(label+'-returned.json',{'returncode':code,'outcome':'UNCONFIRMED','raw_sha256':hashlib.sha256(raw).hexdigest()})
            raise ValueError('CLI_OUTPUT_UNCONFIRMED') from None
        self.save(label+'-returned.json',{'returncode':code,'state':value.get('state'),
            'code':value.get('code'),'raw_sha256':hashlib.sha256(raw).hexdigest()})
        return code,value

    def connect_args(self):
        return ['--profile',PROFILE,'--new-agent','home-r1-local-worker','--name','Home R1 local worker',
                '--client','codex','--candidate-ref',self.p['codex_candidate_ref'],'--project',str(self.root/'workspace'),'--provider-home',self.p['provider_home'],
                '--no-chat','--json',*self.common]

    def prepare(self):
        require(not self.root.exists(), 'FRESH_ROOT_REQUIRED')
        import socket
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',self.p['port']))  # Availability only; no listen or server.
        self.root.mkdir()
        for name in ('workspace','deliverables','public','private'): (self.root/name).mkdir()
        (self.root/'workspace/numbers.csv').write_bytes(b'value\n1.25\n2.50\n-0.75\n7.00\n')
        self.save('prepared.json',{'input_sha256':sha(self.root/'workspace/numbers.csv'),
                                 'baseline_tokens':0,'baseline_calls':0,'provider_called':False})

    def reserve(self, kind):
        require(kind in ('setup','useful'), 'FINITE_CALL_REQUIRED')
        require(not list(self.public.glob('paid-*-fault.json')), 'PAID_CAMPAIGN_CLOSED_AFTER_FAULT')
        existing=list(self.private.glob('call-*-reserved.json'))
        require(len(existing)<2, 'CALL_LIMIT')
        if kind=='setup': require(not existing, 'SETUP_MUST_BE_FIRST')
        else:
            require(len(existing)==1 and (self.private/'call-setup-reserved.json').exists(), 'SETUP_REQUIRED')
            usage=read(self.public/'setup-accounting-final.json')
            require(usage['plan_sha256']==self.plan_sha and usage['terminal_usage_covered'] is True and
                    usage['observed_total']<POLICY['preventive'] and
                    usage['observed_total']+POLICY['reserve']<=POLICY['observed_limit'], 'SETUP_USAGE_UNKNOWN_OR_BUDGET')
        publish(self.private/('call-'+kind+'-reserved.json'),{'plan_sha256':self.plan_sha,'kind':kind,
                'reserved_at':time.time(),'policy':POLICY,'refund':False})

    def setup_usage(self):
        paths=list((self.home/'connection-tests').glob('*/journal.db'))
        require(len(paths)==1, 'SETUP_JOURNAL_NOT_UNIQUE')
        return journal_snapshot(self.root,paths[0],('connection-test','local','session','epoch'))

    def current_scope(self):
        flow=self.flow(); binding=flow.binding()
        value=flow.observe() # GET only; resolves saved original intent, never resubmits.
        require('session' in value, 'EXACT_SESSION_NOT_YET_KNOWN')
        scope=value['session']['scope']
        require(scope['agent_id']=='home-r1-local-worker' and all(scope[k]==binding[k] for k in
                ('server_id','executor_id','binding_id','workspace_id','agent_id')), 'SCOPE_CHANGED')
        require(flow.document.get('work',{}).get('client_intent_id')==USEFUL_ID,'ORIGINAL_INTENT_REQUIRED')
        return flow,binding,value,scope

    def useful_usage(self, scope, epoch):
        digest=hashlib.sha256((scope['executor_id']+'\0'+scope['session_id']).encode('ascii')).hexdigest()
        return journal_snapshot(self.root,self.home/'core-runtime'/('session-'+digest+'.db'),
            (scope['server_id'],scope['executor_id'],scope['session_id'],epoch))


    def inspect_home(self, value, scope):
        operations=value['operations']
        require(operations, 'CANONICAL_OPERATION_REQUIRED')
        operation=operations[-1]
        target={'kind':'execution',**{k:scope[k] for k in ('server_id','workspace_id','executor_id','session_id')},
                'operation_id':operation['operation_id']}
        resolved=self.get('/api/v1/home/target?'+urlencode({'target':json.dumps(target),'workspace_id':scope['workspace_id']}))['data']
        require(resolved.get('available') is True and resolved['target']==target and
                resolved.get('agent_id')==scope['agent_id'], 'HOME_TARGET_MISMATCH')
        overview=self.get('/api/v1/home/overview?'+urlencode({'workspace_id':scope['workspace_id']}))['data']
        require(overview.get('version')==1 and overview.get('server_id')==scope['server_id'], 'HOME_SERVER_CHANGED')
        return {'target':target,'source_revision':resolved['source_revision'],'home_version':1,
                'sections':{k:{'status':overview[k]['status'],'total':overview[k]['total']} for k in
                            ('work','results','attention','agents','external_activity')}}

    def inventory_for(self, request):
        # Use the actual dashboard-mounted runtime-options contract, not the
        # unmounted dashboard inventory_view route. Local byte proof is separate.
        me=self.get('/api/v1/runtime-management/connections/me')
        subject=me['agent_id'] if request.get('agent_creation') else request['agent_id']
        query={'executor_id':request['executor_id']}
        if request.get('workspace_id'):query['workspace_id']=request['workspace_id']
        value=self.get('/api/v1/runtime-management/agents/'+quote(subject,safe='')+'/runtime-options?'+urlencode(query))
        require(value['adapter_freshness'].get('codex_app_server')=='FRESH','INVENTORY_NOT_FRESH')
        require(value['inventory_revision']==request['inventory_revision'],'INVENTORY_REVISION_CHANGED')
        matches=[e for e in value['options'] if e['adapter_id']=='codex_app_server' and
                 e['candidate_ref']==request['candidate_ref']==self.p['codex_candidate_ref']]
        require(len(matches)==1 and matches[0].get('can_configure') is True,'NATIVE_INSTALLATION_CHANGED')
        require(sha(self.p['codex_executable'])==self.p['codex_content_fingerprint'],'NATIVE_BYTES_CHANGED')
        return {'candidate_ref':request['candidate_ref'],'inventory_revision':request['inventory_revision'],
                'freshness':'FRESH','local_executable_sha256':self.p['codex_content_fingerprint'],
                'byte_proof_source':'local approved executable; runtime-options does not expose fingerprint',
                'configuration_capability_report_present':isinstance(matches[0].get('harness_configuration'),dict),
                'ambient_mcp_and_instructions':'NOT_INSPECTED_OR_ISOLATED; native inherited configuration may apply'}

    def review(self):
        self.watched()
        require(not list((self.home/'connection-tests').glob('*/journal.db')), 'FRESH_SETUP_HISTORY_REQUIRED')
        # Installed connect --plan obtains current embedded host/inventory/candidate from canonical GETs.
        # No --candidate-ref guessed and no runtime.version/model call in this path.
        code,value=self.cli('connection-review',['connect','--plan',*self.connect_args()])
        require(code==0 and value.get('state')=='review','CONNECTION_REVIEW_REQUIRED')
        request=value['review_request']
        require(request['configuration']['adapter_id']=='codex_app_server' and
                request['configuration']['workspace_root']==str(self.root/'workspace') and
                request['configuration']['provider_home']==self.p['provider_home'] and
                request.get('agent_creation') is not None,'REVIEW_SCOPE_CHANGED')
        inventory=self.inventory_for(request)
        publish(self.private/'selected-review.json',value)
        self.save('connection-review.json',{'server_id':value['server_id'],'review_revision':value['review_revision'],
            'client_intent_id':request['client_intent_id'],'candidate_ref':request['candidate_ref'],
            'inventory_revision':request['inventory_revision'],'adapter_id':'codex_app_server',
            'configuration_sha256':hashlib.sha256(json.dumps(request['configuration'],sort_keys=True).encode()).hexdigest(),
            'inventory':inventory,'native_test_is_productive':True,'authority':'CANONICAL_OPERATOR_SETUP_REVIEW; grant is created only at Finish'})

    @contained_admission('setup')
    def setup(self, review_revision):
        self.watched()
        review=read(self.private/'selected-review.json')
        require(review_revision==review['review_revision'],'EXACT_REVIEW_REQUIRED')
        require(not list((self.home/'connection-tests').glob('*/journal.db')), 'FRESH_SETUP_HISTORY_REQUIRED')
        self.inventory_for(review['review_request'])
        self.reserve('setup')
        start=time.monotonic(); last_check=0.; last=None
        def monitor():
            nonlocal last_check,last
            if time.monotonic()-last_check<1:return
            last_check=time.monotonic()
            self.watched()
            require(time.monotonic()-start<330,'SETUP_OBSERVATION_DEADLINE')
            try:last=self.setup_usage()
            except ValueError as error:
                if str(error) not in ('SETUP_JOURNAL_NOT_UNIQUE','JOURNAL_NOT_YET_AVAILABLE','STREAM_NOT_YET_AVAILABLE'): raise
                return
            require(last['observed_total']<POLICY['preventive'],'PREVENTIVE_BUDGET_REACHED')
        code,value=self.cli('setup',['connect','--approve',review_revision,'--timeout','300',*self.connect_args()],monitor=monitor)
        last=self.setup_usage()
        self.save('setup-accounting-final.json',last)
        require(code==0 and value.get('state')=='configured' and last['terminal_usage_covered'],
                'SETUP_NOT_COVERED_OR_NOT_CONFIGURED')
        self.save('setup-complete.json',{'configured':True,'productive_call_count':1,'observed_total':last['observed_total']})

    def setup_observe(self):
        require((self.private/'call-setup-reserved.json').exists(),'ORIGINAL_SETUP_RESERVATION_REQUIRED')
        selected=read(self.private/'selected-review.json');request=selected['review_request']
        test=self.get('/api/v1/runtime-management/connections/setup-tests/'+quote(request['client_intent_id'],safe=''))
        require(test['test_id']==request['client_intent_id'],'SETUP_INTENT_CHANGED')
        accounting=self.setup_usage()
        index=len(list(self.public.glob('setup-reconciliation-*.json')))
        self.save(f'setup-reconciliation-{index:04d}.json',{'test_id':test['test_id'],'status':test['status'],
            'stage':test['stage'],'accounting':accounting,'submitted_again':False,
            'new_useful_allowed_by_this_receipt':False,
            'limitation':'GET-only reconciliation does not fabricate a configured profile or overwrite the original apply outcome.'})

    @contained_admission('useful')
    def useful(self):
        self.watched()
        require((self.public/'setup-complete.json').exists(),'SETUP_COMPLETE_REQUIRED')
        require(not (self.root/'deliverables/report.json').exists(),'REPORT_MUST_BE_NEW')
        require(sha(self.root/'workspace/numbers.csv')==read(self.public/'prepared.json')['input_sha256'],'INPUT_CHANGED')
        known=read(self.public/'setup-accounting-final.json')
        fresh=self.setup_usage()
        require(fresh['terminal_usage_covered'] and fresh['observed_total']==known['observed_total'],
                'SETUP_USAGE_CHANGED')
        # Canonical review is non-issuing. No fabricated grant from a local boolean.
        code,grant=self.cli('grant-review',['work','authorize','--minutes','60','--actions','3',*self.work_args])
        require(code==0,'GRANT_REVIEW_FAILED')
        binding=self.flow().binding()
        proof=available_grant(grant,binding,datetime.now(timezone.utc))
        self.save('available-grant.json',{'scope':grant['scope'],'grant':proof,'issued_by_driver':False})
        self.watched(); self.reserve('useful')
        prompt=(f"Read only {self.root/'workspace/numbers.csv'}. Compute the number of data rows, the exact decimal sum "
            f"of the value column, and SHA256 of the original CSV bytes. Write JSON with keys row_count, sum and input_sha256 "
            f"to {self.root/'deliverables/report.json'}, and report completion. Use the approved absolute Python executable "
            f"{self.p['python']['path']} directly; no PATH lookup, network, nested shell, other files or subagents. "
            "If native permission is required for this sibling output location, wait for the operator's canonical decision. "
            "Do not evade a refusal or change the output path. Do not issue further work.")
        begun=time.monotonic(); last_check=0.
        setup_total=read(self.public/'setup-accounting-final.json')['observed_total']
        def dispatch_monitor():
            nonlocal last_check
            if time.monotonic()-last_check<1:return
            last_check=time.monotonic(); self.watched()
            require(time.monotonic()-begun<60,'DISPATCH_RESPONSE_TIMEOUT')
            try:
                _,_,observed,scope=self.current_scope()
                epoch=observed['events'].get('stream_epoch')
                if not epoch: raise ValueError('STREAM_NOT_YET_AVAILABLE')
                usage=self.useful_usage(scope,epoch)
            except ValueError as error:
                if str(error) in ('EXACT_SESSION_NOT_YET_KNOWN','STREAM_NOT_YET_AVAILABLE','JOURNAL_NOT_YET_AVAILABLE') and time.monotonic()-begun<20:
                    return
                raise
            require(setup_total+usage['observed_total']<POLICY['preventive'],'PREVENTIVE_BUDGET_REACHED')
        code,_=self.cli('useful',['work','send','--new-session','--request-id',USEFUL_ID,'--message',prompt,*self.work_args],monitor=dispatch_monitor)
        # An uncertain reply never enters send again. Read only the original durable intent.
        self.save('useful-selection.json',{'request_id':USEFUL_ID,'cli_returncode':code,'replay_allowed':False})
        self.monitor()

    def monitor(self):
        require((self.private/'call-useful-reserved.json').exists(),'ORIGINAL_RESERVATION_REQUIRED')
        if (self.public/'useful-accounting-final.json').exists():
            prior=read(self.public/'useful-accounting-final.json')
            _,_,value,scope=self.current_scope()
            require(scope==prior['scope'] and value['state']==prior['canonical_state'],'TERMINAL_SCOPE_CHANGED')
            latest=self.useful_usage(scope,value['events']['stream_epoch'])
            require(latest['terminal_usage_covered'] and latest['observed_total']==prior['observed_total'],
                    'TERMINAL_USAGE_CHANGED')
            return # Safe resume is GET/RO-only, never another admission.
        # Deadline is persisted UTC, so resuming observation does not renew work lifetime.
        deadline=read(self.private/'call-useful-reserved.json')['reserved_at']+600
        setup=read(self.public/'setup-accounting-final.json')['observed_total']
        last_good=time.monotonic(); latest=None; counter=len(list(self.public.glob('work-observation-*.json')))
        try:
            while time.time()<deadline:
                self.watched()
                observation_started=time.monotonic()
                try:
                    flow,binding,value,scope=self.current_scope()
                    epoch=value['events'].get('stream_epoch')
                    require(isinstance(epoch,str) and epoch,'STREAM_NOT_YET_AVAILABLE')
                    latest=self.useful_usage(scope,epoch)
                except ValueError as error:
                    if str(error) in ('EXACT_SESSION_NOT_YET_KNOWN','STREAM_NOT_YET_AVAILABLE','JOURNAL_NOT_YET_AVAILABLE') and time.monotonic()-last_good<20:
                        time.sleep(.5); continue
                    raise
                require(not value['events'].get('gap_pending'),'CANONICAL_EVENT_GAP')
                require(setup+latest['observed_total']<POLICY['preventive'],'PREVENTIVE_BUDGET_REACHED')
                last_good=time.monotonic()
                home=self.inspect_home(value,scope)
                require(time.monotonic()-observation_started<20 and time.time()<deadline,'OBSERVATION_DEADLINE')
                self.save(f'work-observation-{counter:04d}.json',{'scope':scope,'state':value['state'],
                    'operations':[{k:o.get(k) for k in ('operation_id','executor_stage','admission_state')} for o in value['operations']],
                    'pending_approval_ids':[v['approval_id'] for v in value['requests']['items']],
                    'accounting':latest,'campaign_total':setup+latest['observed_total'],'home':home})
                counter+=1
                if value['state'] in ('completed','failed','blocked','decision_refused'):
                    self.save('useful-accounting-final.json',{**latest,'campaign_total':setup+latest['observed_total'],
                        'canonical_state':value['state'],'scope':scope})
                    require(latest['terminal_usage_covered'],'TERMINAL_USAGE_UNKNOWN')
                    return
                time.sleep(2)
            raise ValueError('WORK_DEADLINE')
        except BaseException:
            self.save('monitor-containment.json',{'latest_accounting':latest,'last_observation_age':time.monotonic()-last_good,
                'reason':'OBSERVATION_OR_BUDGET_OR_DEADLINE','retry_allowed':False})
            self.cleanup()
            raise

    def answer_review(self, approval_id):
        self.watched(); flow,binding,value,scope=self.current_scope()
        detail=flow.decision_detail(approval_id,session_id=scope['session_id'])
        from okto_nexus.application.terminal_connection import document_revision
        key=detail['request_payload']['kwargs']['approval_key']
        require(all(key.get(k)==scope[k] for k in ('server_id','executor_id','binding_id','workspace_id','agent_id','session_id')),
                'NATIVE_APPROVAL_SCOPE_CHANGED')
        self.save('native-review-'+approval_id+'.json',{'approval_id':approval_id,'scope':scope,
            'revision':document_revision(detail['request_payload']['kwargs']),
            'decision_selected':False,'view_command_in_existing_home_only':True})

    def close(self):
        flow,binding,value,scope=self.current_scope()
        require(value['state'] in ('completed','failed'),'TERMINAL_WORK_REQUIRED')
        self.cli('close',['work','close','--session-id',scope['session_id'],'--request-id','home-r1-close-01',*self.work_args])
        until=time.monotonic()+45
        while time.monotonic()<until:
            session=flow.session(binding,scope['session_id'])
            if session['lifecycle_state']=='CLOSED':
                self.save('closed-session.json',{'scope':scope,'lifecycle_state':'CLOSED','continuation_posts':0,
                                               'home_ui_refusal_not_yet_observed':True})
                return
            time.sleep(1)
        raise ValueError('SESSION_CLOSE_NOT_CONFIRMED')

    def verify_report(self):
        import csv
        from decimal import Decimal
        from io import StringIO
        path=owned(self.root,self.root/'deliverables/report.json')
        require(path.stat().st_size<=4096,'REPORT_LIMIT')
        data=read(path); raw=(self.root/'workspace/numbers.csv').read_bytes()
        require(hashlib.sha256(raw).hexdigest()==read(self.public/'prepared.json')['input_sha256'],'INPUT_CHANGED')
        rows=list(csv.DictReader(StringIO(raw.decode('utf-8'))))
        expected=sum((Decimal(r['value']) for r in rows),Decimal(0))
        require(type(data.get('row_count')) is int and data['row_count']==len(rows) and
                Decimal(str(data.get('sum')))==expected and data.get('input_sha256')==hashlib.sha256(raw).hexdigest(),
                'REPORT_NOT_CORRECT')
        self.save('report-verification.json',{'row_count':len(rows),'sum':str(expected),
            'input_sha256':hashlib.sha256(raw).hexdigest(),'report_sha256':sha(path),'independent_decimal_check':True})

    def record_presentation(self, proof_path, proof_sha):
        require(sha(proof_path)==proof_sha,'BROWSER_PROOF_CHANGED')
        proof=read(proof_path); _,_,value,scope=self.current_scope()
        require(proof.get('campaign_id')==self.p['campaign_id'] and proof.get('scope')==scope,
                'BROWSER_SCOPE_CHANGED')
        require(proof.get('presentation_only_disabled') is True and proof.get('same_operation_before_after') is True
                and proof.get('runtime_control_posts')==0 and proof.get('actual_browser_observed') is True,
                'PRESENTATION_BROWSER_PROOF_REQUIRED')
        selected=self.watched()
        self.save('presentation-observation.json',{'browser_proof_sha256':proof_sha,'scope':scope,
            'owner':selected['owner'],'cohort':selected['cohort'],'canonical_state':value['state'],
            'limitation':'Browser action is evidenced separately; no runtime effects are performed by this recorder.'})

    def cleanup(self):
        # Current own home/instance defines scope; never an old hard-coded PID prerequisite.
        from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
        status=self.status(); cohorts=[]
        if status['state']!='stopped':
            selected,handles=self.capture(); cohorts.append((selected,handles))
        try:
            if status['state']!='stopped':
                try:
                    _,_,value,scope=self.current_scope()
                    if value['state'] not in ('completed','failed') and not (self.private/'interrupt-reserved.json').exists():
                        self.cli('interrupt',['work','interrupt','--session-id',scope['session_id'],
                            '--request-id','home-r1-interrupt-01',*self.work_args])
                except BaseException:
                    pass # Canonical own-service drain remains the containment path; no request replay.
                if not (self.private/'stop-normal-reserved.json').exists():
                    self.cli('stop-normal',['service','stop','--timeout','45','--json',*self.common])
                end=time.monotonic()+120
                while time.monotonic()<end:
                    if all(h.exited() for _,hs in cohorts for h in hs.values()) and self.status()['state']=='stopped':break
                    time.sleep(.5)
                current=self.status()
                if current['state']!='stopped':
                    require(self.p.get('own_cleanup_force_within_standing_stop_authority') is True,'OWN_FORCE_SELECTION_REQUIRED')
                    selected,new_handles=self.capture(); cohorts.append((selected,new_handles))
                    self.cli('stop-force',['service','stop','--force','--expected-generation',selected['owner']['generation'],
                                          '--timeout','45','--json',*self.common])
            end=time.monotonic()+60
            while cohorts and time.monotonic()<end and not all(h.exited() for _,hs in cohorts for h in hs.values()):time.sleep(.2)
            require(not cohorts or all(h.exited() for _,hs in cohorts for h in hs.values()),'PHYSICAL_EXIT_UNKNOWN')
            require(self.status()['state']=='stopped','CANONICAL_ABSENCE_REQUIRED')
            if not cohorts:
                proof=read(self.public/'exit-proof.json')
                require(proof.get('plan_sha256')==self.plan_sha and proof.get('physical_exit_confirmed') is True
                        and set(proof.get('processes',{}))==set(ROLES), 'RETAINED_EXIT_PROOF_REQUIRED')
            install=ServerInstallation(self.home,self.home/'nexus.db'); _,task=install.observe()
            require(task is not None and not task.active and task.state not in (0,2,4),'TASK_INACTIVE_REQUIRED')
            self.save('cleanup.json',{'state':'stopped','task_inactive':True,'data_preserved':True,
                'cohorts':[{'selected':s,'processes':{r:{'pid':h.pid,'birth':h.birth,'exit_code':h.exit_code()} for r,h in hs.items()}} for s,hs in cohorts],
                'physical_exit_confirmed':True,'work_settlement':'NOT_ASSERTED'})
            self.cli('uninstall',['service','uninstall','--user','--json',*self.common])
            _,task=install.observe()
            require(task is None,'TASK_ABSENCE_REQUIRED')
            self.save('uninstalled.json',{'task_absent':True,'data_preserved':True,'work_settlement':'NOT_ASSERTED'})
        finally:
            for _,handles in cohorts:
                for h in handles.values():h.close()


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',required=True); parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--authorization'); parser.add_argument('--authorization-sha256')
    parser.add_argument('action',choices=['prepare','install','start','watch','review','setup','useful','observe','answer-review',
                                        'close','verify-report','record-presentation','setup-observe','cleanup'])
    parser.add_argument('--review-revision'); parser.add_argument('--approval-id')
    parser.add_argument('--browser-proof'); parser.add_argument('--browser-proof-sha256')
    a=parser.parse_args(argv); d=Driver(a.plan,a.plan_sha256,authorization=a.authorization,authorization_sha=a.authorization_sha256)
    if a.action in ('install','start'):
        require((d.public/'prepared.json').exists(),'PREPARE_REQUIRED')
        if a.action=='start':require(read(d.public/'install-returned.json')['returncode']==0,'INSTALL_REQUIRED')
        extra=['--user','--start-at-login'] if a.action=='install' else ['--timeout','45']
        code,_=d.cli(a.action,['service',a.action,*extra,'--json',*d.common])
        require(code==0,'SERVICE_COMMAND_NOT_CONFIRMED')
    elif a.action=='setup':d.setup(a.review_revision)
    elif a.action=='answer-review':d.answer_review(a.approval_id)
    elif a.action=='observe':d.monitor()
    elif a.action=='setup-observe':d.setup_observe()
    elif a.action=='verify-report':d.verify_report()
    elif a.action=='record-presentation':d.record_presentation(a.browser_proof,a.browser_proof_sha256)
    else:getattr(d,a.action)()
    print(json.dumps({'action':a.action,'completed':True,'campaign_id':d.p['campaign_id']}))


if __name__=='__main__':
    try: main()
    except (ValueError,KeyError,OSError,TypeError) as error:
        print(json.dumps({'completed':False,'error_type':type(error).__name__,
                          'code':str(error) if isinstance(error,ValueError) else 'OWN_CAMPAIGN_UNCONFIRMED'}))
        raise SystemExit(1)
