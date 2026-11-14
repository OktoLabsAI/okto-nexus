"""Installed CLI handlers on the existing single API worker.

The factory hook delegates to installed open_work after run_work has selected,
inspected and locked the target. It only observes methods and wraps transport;
it does not replace the parser, service inspection, lock, checkpoint or display.
Raw CLI output goes to the outer runner's private stdout, never a public report.
"""
from pathlib import Path
import threading

from okto_nexus.adapters.inbound.cli import work as cli
from okto_nexus.application.terminal_connection import ConnectionError
import token_collector as tokens


class CLIFlow:
    def __init__(self,service,profile,service_args,operator_profile=None):
        self.home=Path(service.adapter.home).resolve();self.profile=profile
        self.args=['--profile',profile,'--json',*map(str,service_args)]
        if operator_profile:self.args+=['--operator-profile',operator_profile]
        self._flow=cli.open_work(service,profile)
        self._raw=self._flow.call
        self.call=self._dispatch
        self._flow.call=self.call
        self.expected_scope=None;self.expected_actor=None;self.expected_session=None
        self.outcomes=[];self.command_count=0;self._command_readonly=False
        self._owner=threading.get_ident()
        self.timeout=30
        self.set_timeout(self.timeout)

    def set_timeout(self,value):
        self.timeout=value
        if hasattr(self._raw,'timeout'):self._raw.timeout=value

    def _dispatch(self,method,path,body=None):
        if self._command_readonly and method!='GET':
            raise ConnectionError('CLI_RECOVERY_EFFECT_REFUSED','This observation cannot submit an effect.')
        return self._raw(method,path,body)

    @property
    def document(self):return self._flow.document

    def expect(self,scope,actor,session=None):
        if threading.get_ident()!=self._owner:raise RuntimeError('CLI_EXPECT_OWNER_REQUIRED')
        self.expected_scope={key:scope[key] for key in tokens.PRE_SCOPE}
        self.expected_actor=actor;self.expected_session=session

    def binding(self):
        self._flow.call=self.call
        return self._flow.binding()

    def api(self,method,path,body=None):
        if method!='GET':raise ValueError('READ_ONLY_API_REQUIRED')
        self._flow.call=self.call
        return self._flow.api(method,path,body)

    def operation(self,*args,**kwargs):
        self._flow.call=self.call
        return self._flow.operation(*args,**kwargs)

    def session(self,*args,**kwargs):
        self._flow.call=self.call
        return self._flow.session(*args,**kwargs)

    def diagnostics(self):
        return {'command_count':self.command_count,'recent':[{
            key:item[key] for key in ('action','exit_code','handler_entered','error_type','possible_effect')
        } for item in self.outcomes[-32:]],'entrypoint':'INSTALLED_RUN_WORK_PARSER_AND_HANDLERS',
        'stdout':'OUTER_RUNNER_PRIVATE_CAPTURE','console_subprocess_proven':False}

    def _execute(self,action,options,handler,*,readonly=False):
        if threading.get_ident()==self._owner:raise RuntimeError('CLI_REQUIRES_API_WORKER')
        if self.expected_scope is None or self.expected_actor is None:
            raise RuntimeError('CLI_EXPECTED_SCOPE_REQUIRED')
        factory=cli.open_work;capture={};self._command_readonly=readonly
        outcome={'action':action,'exit_code':None,'handler_entered':False,'error_type':None,'possible_effect':False}
        def opened(service,profile,connection=None):
            if Path(service.adapter.home).resolve()!=self.home or profile!=self.profile:
                raise ConnectionError('CLI_TARGET_CHANGED','The selected CLI target changed.')
            flow=factory(service,profile) if connection is None else factory(service,profile,connection)
            self._raw=flow.call;flow.call=self.call
            self.set_timeout(self.timeout)
            # Installed run_work already owns the profile guard here. Validate
            # against the controller's original selection, not a newly selected scope.
            binding=flow.binding();me=flow.api('GET','/connections/me')
            if ({key:binding[key] for key in tokens.PRE_SCOPE}!=self.expected_scope
                    or me['server_id']!=self.expected_scope['server_id'] or me['agent_id']!=self.expected_actor
                    or flow.document.get('session_id')!=self.expected_session):
                raise ConnectionError('CLI_SCOPE_CHANGED','The CLI selection no longer matches the reserved work.')
            self._flow=flow
            original=getattr(flow,handler)
            def observed(*args,**kwargs):
                outcome['handler_entered']=True
                try:
                    value=original(*args,**kwargs);capture['value']=value
                    return value
                except BaseException as error:
                    capture['error']=error
                    raise
            setattr(flow,handler,observed)
            return flow
        def guarded_factory(*args,**kwargs):
            try:return opened(*args,**kwargs)
            except BaseException as error:
                capture['error']=error
                raise
        cli.open_work=guarded_factory
        try:
            outcome['exit_code']=cli.run_work([action,*options,*self.args])
        except BaseException as error:
            capture.setdefault('error',error)
            raise
        finally:
            cli.open_work=factory;self._command_readonly=False
            error=capture.get('error');outcome['error_type']=type(error).__name__ if error else None
            outcome['possible_effect']=bool(getattr(error,'possible_effect',False))
            outcome['handler_value']=capture.get('value');outcome['private_error']=error
            if (self.expected_session is None or '--new-session' in options) and outcome['handler_entered'] and action=='send':
                # Only the actual admitted handler's validated resolution can
                # establish the first session, including a lost admission reply.
                self.expected_session=self._flow.document.get('session_id')
            self.command_count+=1;self.outcomes.append(outcome);self.outcomes=self.outcomes[-128:]
        if capture.get('error') is not None:
            # The actual handler error, observed before installed CLI presentation,
            # preserves existing known-loss recovery. Exit3 alone is never an error.
            raise capture['error']
        if not outcome['handler_entered'] or 'value' not in capture:
            error=ConnectionError('CLI_NOT_DISPATCHED','The CLI refused before its selected handler.')
            outcome['error_type']=type(error).__name__;outcome['private_error']=error
            raise error
        value=capture['value']
        displayed=value.get('events',value) if action=='events' and isinstance(value,dict) else value
        expected=3 if isinstance(displayed,dict) and displayed.get('state') in (
            'blocked','submission_unconfirmed','failed','decision_refused') else 0
        if outcome['exit_code']!=expected:
            error=ConnectionError('CLI_OUTCOME_UNCONFIRMED','The handler and CLI presentation outcomes disagree.',
                                  possible_effect=not readonly)
            outcome['error_type']=type(error).__name__;outcome['private_error']=error
            outcome['possible_effect']=error.possible_effect
            raise error
        return value

    def submit(self,text=None,*,client_intent_id,new_session=False,**kwargs):
        if kwargs:raise ValueError('CLI_SUBMISSION_OPTIONS_NOT_APPROVED')
        options=['--message',text,'--request-id',client_intent_id]
        if new_session:options+=['--new-session']
        elif self.expected_session:options+=['--session-id',self.expected_session]
        value=self._execute('send',options,'submit')
        if (self.expected_session is None or new_session) and isinstance(value,dict):
            self.expected_session=value.get('scope',{}).get('session_id')
        return value

    @staticmethod
    def _observation_options(session_id=None,after_sequence=0,stream_epoch=None,slot_name='work'):
        options=['--after-sequence',str(after_sequence)]
        if session_id:options+=['--session-id',session_id]
        if stream_epoch:options+=['--stream-epoch',stream_epoch]
        if slot_name=='control':options+=['--control']
        elif slot_name!='work':raise ValueError('CLI_SLOT_INVALID')
        return options

    def observe(self,**kwargs):
        return self._execute('status',self._observation_options(**kwargs),'observe',readonly=True)

    def events(self,**kwargs):
        return self._execute('events',self._observation_options(**kwargs),'observe',readonly=True)

    def sessions(self):return self._execute('sessions',[],'sessions',readonly=True)

    def decision_detail(self,approval_id,*,session_id=None):
        options=['--approval-id',approval_id]
        if session_id:options+=['--session-id',session_id]
        return self._execute('answer',options,'decision_detail',readonly=True)

    def decide(self,approval_id,decision,*,reviewed_revision=None,session_id=None,response=None):
        if response is not None:raise ValueError('CLI_ANSWER_FILE_NOT_IN_FINITE_CAMPAIGN')
        options=['--approval-id',approval_id,'--decision',decision,'--review',reviewed_revision]
        if session_id:options+=['--session-id',session_id]
        return self._execute('answer',options,'decide')
