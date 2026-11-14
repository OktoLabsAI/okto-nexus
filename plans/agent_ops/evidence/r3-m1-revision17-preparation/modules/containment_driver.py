"""Existing local canonical controls after the work runner's failed normal stop."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from normal_containment import run

PREFIX='/api/v1/runtime-management'

def require(ok,code):
    if not ok:raise RuntimeError(code)

class LocalControl:
    def __init__(self,context,controller,request):
        from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
        self.context=context;self.controller=controller;self.record=controller.data['requests'][request]
        require(self.record['lane']=='local','LOCAL_CONTAINMENT_ONLY')
        selected=json.loads((context.PUBLIC/'nexus-owner-selection.json').read_bytes())
        context.common.require_tags(selected,context)
        self.expected={key:selected[key] for key in ('pid','birth_filetime','generation')}
        self.instance=selected['instance_id']
        pin=context.P['execution_bundle']['files']['root_driver_observation']
        require(hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()==pin['sha256'],'OBSERVER_CHANGED')
        spec=importlib.util.spec_from_file_location('containment_process_observer',pin['path'])
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        self.handle=None
        self.proof_path=context.PUBLIC/'nexus-exit-proof.json'
        if self.watcher_proof() is None:
            try:self.handle=module.PhysicalProcess(self.expected['pid'])
            except Exception as error:
                # A missing handle is not an exit proof. The original watcher
                # may still be publishing its retained-handle observation.
                if str(error)!='PROCESS_HANDLE_UNAVAILABLE':raise
            if self.handle is not None:
                try:require(self.handle.birth()==self.expected['birth_filetime'],'OWNER_BIRTH_CHANGED')
                except BaseException:self.handle.close();self.handle=None;raise
        self.http=LocalOperatorHTTP(host='127.0.0.1',port=58631,timeout=10)
        state=controller.accounting;stream=state['streams'].get(self.record.get('stream'))
        self.scope=stream['scope'] if stream else None
        matches=[turn for turn in state['turns'].values()
                 if turn['operation_id']==self.record.get('operation') and turn['started'] and not turn['terminal']]
        require(len(matches)<=1,'NATIVE_TURN_AMBIGUOUS')
        self.exact_turn=({'session_id':self.record['session'],'operation_id':self.record['operation'],
                         'native_turn_id':matches[0]['turn_id']} if matches else None)
        self.first_stop=json.loads((context.PUBLIC/'lifecycle-nexus-stop-result.json').read_bytes())

    def save(self,name,value):
        path=self.context.PUBLIC/('normal-containment-'+name+'.json')
        with path.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(value,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())

    def watcher_proof(self):
        if not self.proof_path.exists():return None
        proof=json.loads(self.proof_path.read_bytes())
        self.context.common.require_tags(proof,self.context)
        require(all(proof.get(key)==value for key,value in self.expected.items())
            and proof.get('instance_id')==self.instance and proof.get('component')=='nexus'
            and proof.get('retained_handle') is True and proof.get('exit_confirmed') is True
            and proof.get('force_used') is False and proof.get('wait_result')==0,
            'WATCHER_EXIT_PROOF_CHANGED')
        return proof

    def physical_exit(self):
        proof=self.watcher_proof()
        if proof is not None:return proof
        if self.handle is not None and self.handle.wait(0):
            return {**self.expected,'retained_handle':True,'exit_confirmed':True,'force_used':False}
        return None

    def observe_owner(self):
        if self.handle is None or self.handle.wait(0):return None
        value=self.http('GET','/api/v1/service')['data']
        require(value.get('instance_id')==self.instance,'INSTANCE_CHANGED')
        return {key:value.get(key) for key in ('pid','generation','state','ready_for_queries')}|{
                'birth_filetime':self.handle.birth()}

    def observe_turn(self,exact):
        if exact is None:return 'unknown'
        value=self.http('GET',PREFIX+'/runtime/operations/'+exact['operation_id'])
        require(value.get('scope')==self.scope and value.get('operation_id')==exact['operation_id'],
                'ORIGINAL_OPERATION_CHANGED')
        if value.get('executor_stage') in ('SUCCEEDED','FAILED','CANCELLED'):return 'terminal'
        return 'active' if value.get('admission_state') in ('ACCEPTED','DISPATCHED') else 'unknown'

    def interrupt(self,exact,boundary,deadline):
        require(exact==self.exact_turn and self.scope is not None,'EXACT_TURN_CHANGED')
        request={key:self.scope[key] for key in ('agent_id','binding_id','workspace_binding_id','session_id')}
        request.update(client_intent_id='m1-contain-'+exact['operation_id'],intent='turn.interrupt',
                       target={'kind':'native_turn_id','expected_turn_id':exact['native_turn_id']})
        self.save('resolve-selected',request);boundary()
        self.http.timeout=min(10,max(.001,deadline-time.monotonic()))
        require(time.monotonic()<deadline,'NORMAL_CONTAINMENT_DEADLINE')
        resolved=self.http('POST',PREFIX+'/runtime/intents:resolve',request)
        require(resolved.get('scope')==self.scope and resolved.get('client_intent_id')==request['client_intent_id']
            and resolved.get('semantic_intent',{}).get('action')=='turn.interrupt'
            and resolved.get('semantic_intent',{}).get('target')==request['target']
            and resolved.get('can_submit') is True and resolved.get('blockers')==[],'INTERRUPT_RESOLUTION_CHANGED')
        admission={key:resolved[key] for key in ('client_intent_id','operation_id','resolution_revision','intent_hash')}
        self.save('admit-selected',admission);boundary()
        self.http.timeout=min(10,max(.001,deadline-time.monotonic()))
        require(time.monotonic()<deadline,'NORMAL_CONTAINMENT_DEADLINE')
        value=self.http('POST',PREFIX+'/runtime/operations',admission)
        require(value.get('scope')==self.scope and value.get('operation_id')==admission['operation_id']
            and value.get('intent_hash')==admission['intent_hash'] and value.get('action')=='turn.interrupt',
            'INTERRUPT_ADMISSION_CHANGED')
        return {'admitted':value.get('admission_state') in ('ACCEPTED','DISPATCHED'),
                'operation_id':value['operation_id'],'admission_state':value.get('admission_state')}

    def normal_stop(self,boundary,deadline):
        boundary()
        remaining=deadline-time.monotonic()
        require(remaining>0,'NORMAL_CONTAINMENT_DEADLINE')
        self.http.timeout=min(50,remaining)
        try:
            value=self.http('POST','/api/v1/service/stop',{'instance_id':self.instance,
                'generation':self.expected['generation'],'timeout_seconds':min(45.0,remaining),'force':False})
        finally:self.http.timeout=10
        body=value.get('data',value)
        require(body.get('instance_id')==self.instance and body.get('generation')==self.expected['generation'],
                'STOP_IDENTITY_CHANGED')
        return {'canonical_stop_returned':True,'shutdown_state':body.get('shutdown',{}).get('state'),'force_used':False}

    def close(self):
        if self.handle is not None:self.handle.close()

def finish_failed_stop(context,controller,request,*,driver_factory=LocalControl,clock=time.monotonic,sleep=time.sleep):
    controller.fence.close()  # before observing or attempting any cleanup control
    started=clock()
    driver=driver_factory(context,controller,request)
    try:
        return run(expected_owner=driver.expected,exact_turn=driver.exact_turn,
            first_stop_result=driver.first_stop,observe_owner=driver.observe_owner,
            observe_turn=driver.observe_turn,physical_exit=driver.physical_exit,
            interrupt=driver.interrupt,normal_stop=driver.normal_stop,save=driver.save,
            close_admissions=controller.fence.close,clock=clock,sleep=sleep,
            timeout_seconds=max(0,180-(clock()-started)))
    finally:driver.close()
