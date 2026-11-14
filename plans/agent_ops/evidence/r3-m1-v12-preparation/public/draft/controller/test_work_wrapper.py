"""Whole candidate wrapper through fake canonical calls and real synthetic Core journals."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sys
import threading
import types

import pytest

from test_independent import (CanonicalFixture,JournalFixture,create_control,scope,deny_external)
from controller import Controller,POLICY
from independent_journal import CoreJournalReader


class FakeHTTP:
    def __init__(self,flow):self.flow=flow;self.timeout=30
    def __call__(self,method,path,body=None):return self.flow.raw(method,path,body)


class WrapperFlow:
    def __init__(self,context,home,lane):
        self.context,self.home,self.lane=context,home,lane
        self.selected=scope(lane)
        self.path=home/'terminal/work'/(context.P['execution_bundle']['profiles'][lane]+'.json')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.document=json.loads(self.path.read_text()) if self.path.exists() else {}
        self.call=FakeHTTP(self)

    def binding(self):return self.call('GET','/api/v1/runtime-management/connections/bindings/'+self.selected['binding_id'])
    def api(self,method,path,body=None):return self.call(method,'/api/v1/runtime-management'+path,body)
    def operation(self,operation_id,binding):return self.api('GET','/runtime/operations/'+operation_id)
    def observe(self,**kwargs):return self.api('GET','/runtime/sessions/'+self.selected['session_id']+'/events')

    def raw(self,method,path,body=None):
        assert threading.get_ident()!=self.context.main_thread,'API call escaped serial worker'
        self.context.calls.append((self.lane,method,path))
        if method=='GET':
            if path.endswith('/connections/me'):return {'server_id':'server','agent_id':'operator'}
            if '/connections/bindings/' in path:return self.selected
            if '/events' in path:return {'events':{'events':[],'gap_pending':False,'has_more':False},'requests':{'items':[]}}
            if '/runtime/operations/' in path:
                return {'operation_id':path.rsplit('/',1)[1],'scope':self.selected,'executor_stage':'SUCCEEDED',
                    'admission_state':'RESOLVED_TERMINAL','action':'turn.submit','possible_effect':True,
                    'result':{'output_text':'10'}}
            raise AssertionError('unplanned GET '+path)
        assert path.endswith('/runtime/operations')
        request=body['client_intent_id'];continuation=self.document['work']['intent']=='turn.submit'
        saved=json.loads((self.context.ROOT/'private/controller.json').read_text())
        assert request in saved['requests'] and request in saved['collector']['state']['requests']
        response=self.context.fixture.admit(request,self.selected,continuation=continuation)
        if self.lane not in self.context.writers:
            owner=self.home if self.lane=='local' else Path(self.context.P['paths']['connector_state'])
            reader=CoreJournalReader(self.context.ROOT,owner,self.lane)
            self.context.writers[self.lane]=JournalFixture(reader.path(self.selected),self.selected)
        total=20 if continuation else 10
        if hasattr(self.context,'before_events'):self.context.before_events(self,request)
        self.context.writers[self.lane].complete(request,total,thread='native-'+self.lane)
        self.context.fixture.terminal(request,self.selected)
        out=Path(self.context.P['paths']['local_deliverables' if self.lane=='local' else 'remote_deliverables'])/'report.json'
        if not continuation:out.write_text(json.dumps(self.context.P['finite_work']['delivery']['expected_shape']))
        return response|{'intent_hash':body['intent_hash']}

    def submit(self,text=None,*,client_intent_id,new_session=False,**kwargs):
        self.binding() # Keep current canonical validation in the worker.
        body={'client_intent_id':client_intent_id,'operation_id':('open-' if new_session else 'turn-')+client_intent_id,
              'intent_hash':'synthetic-hash','resolution_revision':1}
        self.document={'scope':self.selected,'session_id':self.selected['session_id'],'work':
            {'client_intent_id':client_intent_id,'submission':body,'state':'submit_submitted','action':'send',
             'intent':'runtime.start' if new_session else 'turn.submit'}}
        self.path.write_text(json.dumps(self.document),encoding='utf-8')
        result=self.api('POST','/runtime/operations',body)
        self.document['work']['state']='admitted';self.path.write_text(json.dumps(self.document),encoding='utf-8')
        return result


class Context:
    def __init__(self,root):
        self.ROOT=root;self.main_thread=threading.get_ident();self.calls=[];self.writers={}
        self.modules=Path(__file__).parent
        paths={name:str(root/name) for name in ('server_home','operator_home','connector_state','local_project',
            'remote_project','local_deliverables','remote_deliverables')}
        for path in paths.values():Path(path).mkdir()
        for name in ('private','public'):(root/name).mkdir()
        for name in ('server_home','operator_home'):(Path(paths[name])/'terminal/profiles').mkdir(parents=True)
        self.fixture=CanonicalFixture(Path(paths['server_home']))
        self.P={'paths':paths,'package_pins':{'fixture':'NO_REAL_PRODUCT_EXECUTION'},
            'execution_bundle':{'profiles':{'local':'m1v12-local','connector':'m1v12-remote'},'operator_profile':'m1v12-human',
                'files':{'response_loss':{'path':str(self.modules.parent/'response_loss.py')}}},
            'request_ids':{'work':['m1v12-'+lane+'-work-'+number for lane in ('local','remote') for number in ('01','02')]},
            'finite_work':{'request':'Synthetic finite fixture','continuation':'Synthetic continuation',
                'delivery':{'expected_shape':{'row_count':4,'sum':10,'input_sha256':'synthetic'}}}}
        self.C={'service_selection_args':['--home',paths['server_home']]}
        for lane,home_key in [('local','server_home'),('connector','operator_home')]:
            target=Path(paths[home_key])/'terminal/profiles'/(self.P['execution_bundle']['profiles'][lane]+'.json')
            target.write_text(json.dumps({'selection':{'operator_profile':None if lane=='local' else 'm1v12-human'}}))
        initial=create_control(root);initial.close()
        (root/'controller.json').rename(root/'private/controller.json')

    def controller(self):
        approval=self.ROOT/'synthetic-approval.json'
        return Controller(self.ROOT/'private/controller.json',self.ROOT,
            approval_path=approval,approval_sha256=hashlib.sha256(approval.read_bytes()).hexdigest(),expected_proposal_sha256='a'*64)


def test_whole_work_wrapper_local_continuation_remote_lost_response_and_continuation(tmp_path,monkeypatch):
    context=Context(tmp_path)
    module=types.ModuleType('campaign_context')
    module.load=lambda:context
    def require(value,reason):
        if not value:raise AssertionError(reason)
    module.require=require
    monkeypatch.setitem(sys.modules,'campaign_context',module)
    supervisor=types.ModuleType('supervisor_check');supervisor.require_work_owner=lambda selected:None
    monkeypatch.setitem(sys.modules,'supervisor_check',supervisor)
    import okto_nexus.adapters.inbound.cli.work as product_work
    import okto_nexus.adapters.inbound.cli.terminal_target as target
    def service(args,name,operator,resolver):
        lane='local' if name=='m1v12-local' else 'connector'
        home=Path(context.P['paths']['server_home' if lane=='local' else 'operator_home'])
        return types.SimpleNamespace(adapter=types.SimpleNamespace(home=home),lane=lane,inspect=lambda:{'state':'ready'})
    monkeypatch.setattr(target,'resolve_terminal_target',service)
    monkeypatch.setattr(product_work,'open_work',lambda selected,name:WrapperFlow(context,selected.adapter.home,selected.lane))
    results=[]
    try:
        for lane,phase in [('local','useful'),('local','continuation'),('connector','useful'),('connector','continuation')]:
            context.remaining=[lane,phase]
            runpy.run_path(str(Path(__file__).parent.parent/'m1_v12_work.py'),run_name='__main__')
            profile=context.P['execution_bundle']['profiles'][lane]
            suffix='01' if phase=='useful' else '02'
            value=json.loads((tmp_path/'public'/(profile+'-work-'+suffix+'-result.json')).read_text())
            assert value['record']['settled'] and value['canonical_receipt']['executor_stage']=='SUCCEEDED'
            assert value['summary']['reasons']==[] and value['summary']['current']==[]
            if phase=='useful':assert value['useful_result_confirmed']
            else:assert value['canonical_receipt']['standalone_10_mentions']==1
            if lane=='connector' and phase=='useful':
                assert value['submission_error']['stage']=='m1_response_loss'
                assert value['response_loss']['faults']['admission']['phase']=='consumed'
            results.append(value)
        assert len([v for v in context.calls if v[1]=='POST'])==4
        assert results[-1]['summary']['new_reserved_requests']==4
        assert results[-1]['summary']['known_observed_tokens']==POLICY['carry_in_tokens']+20+20
    finally:
        for writer in context.writers.values():writer.close()


def test_cadence_miss_fences_once_then_drains_late_usage_before_public_result(tmp_path,monkeypatch):
    from controller import Refused
    from api_worker import Fenced
    import subprocess
    context=Context(tmp_path);context.remaining=['local','useful']
    entered=threading.Event();release=threading.Event();now=[1000.];ticks=[];controls=[];stops=[]
    def before_events(flow,request):
        entered.set();assert release.wait(15)
    context.before_events=before_events
    context.stop_argv=lambda component:['SYNTHETIC-NORMAL-STOP',component]
    context.env=lambda:{}
    def fake_stop(argv,**kwargs):
        assert argv==['SYNTHETIC-NORMAL-STOP','nexus']
        stops.append(argv)
        return types.SimpleNamespace(pid=123456,returncode=1,poll=lambda:1)
    monkeypatch.setattr(subprocess,'Popen',fake_stop)
    base_controller=context.controller
    def selected_controller():
        control=base_controller();controls.append(control)
        control._monotonic=lambda:now[0];control.fence.clock=lambda:now[0]
        original=control.poll
        def poll():
            if entered.is_set():
                ticks.append(now[0])
                if len(ticks)==1:now[0]+=1.038
                if len(ticks)==4:release.set()
            return original()
        control.poll=poll
        return control
    context.controller=selected_controller
    module=types.ModuleType('campaign_context');module.load=lambda:context
    def require(value,reason):
        if not value:raise AssertionError(reason)
    module.require=require;monkeypatch.setitem(sys.modules,'campaign_context',module)
    import okto_nexus.adapters.inbound.cli.work as product_work
    import okto_nexus.adapters.inbound.cli.terminal_target as target
    home=Path(context.P['paths']['server_home'])
    monkeypatch.setattr(target,'resolve_terminal_target',lambda *args:
        types.SimpleNamespace(adapter=types.SimpleNamespace(home=home),lane='local',inspect=lambda:{'state':'ready'}))
    monkeypatch.setattr(product_work,'open_work',lambda selected,name:WrapperFlow(context,home,'local'))
    try:
        runpy.run_path(str(Path(__file__).parent.parent/'m1_v12_work.py'),run_name='__main__')
        control=controls[0]
        value=json.loads((tmp_path/'public/m1v12-local-work-01-result.json').read_text())
        assert len(stops)==1 and len(ticks)>=4 and control.api.thread is None
        assert value['summary']['reasons']==['MONITOR_CADENCE_EXCEEDED']
        assert value['summary']['new_reserved_requests']==1
        assert value['summary']['known_observed_tokens']==POLICY['carry_in_tokens']+10
        assert value['record']['settled'] and not value['useful_result_confirmed']
        assert value['stop_wrapper_exits']==[1]
        assert value['independent_observation']['worker_in_flight'] is False
        assert value['maximum_poll_start_interval_seconds']==pytest.approx(1.038)
        assert len([call for call in context.calls if call[1]=='POST'])==1
        assert control.data['independent_owner_stops']['local']['native_exit_confirmed'] is False
        with pytest.raises(Fenced):control.fence.require('POST')
        with pytest.raises(Refused):
            control.start_work('forbidden','local','no',binding=scope('local'),checkpoint={})
        assert control.summary()['new_reserved_requests']==1
    finally:
        release.set()
        for control in controls:control.close()
        for writer in context.writers.values():writer.close()


@pytest.mark.parametrize('phase',['snapshot_read','schema_initialization'])
def test_pre_admission_reader_error_publishes_final_blocked_snapshot_without_post(tmp_path,monkeypatch,phase):
    import sqlite3,subprocess
    from independent_journal import CanonicalIntentReader,ReadOnly
    context=Context(tmp_path);context.remaining=['local','useful']
    context.stop_argv=lambda component:['SYNTHETIC-NORMAL-STOP',component];context.env=lambda:{}
    stops=[]
    monkeypatch.setattr(subprocess,'Popen',lambda argv,**kwargs:
        stops.append(argv) or types.SimpleNamespace(pid=12345,returncode=1,poll=lambda:1))
    module=types.ModuleType('campaign_context');module.load=lambda:context
    def require(value,reason):
        if not value:raise AssertionError(reason)
    module.require=require;monkeypatch.setitem(sys.modules,'campaign_context',module)
    import okto_nexus.adapters.inbound.cli.work as product_work
    import okto_nexus.adapters.inbound.cli.terminal_target as target
    home=Path(context.P['paths']['server_home'])
    monkeypatch.setattr(target,'resolve_terminal_target',lambda *args:
        types.SimpleNamespace(adapter=types.SimpleNamespace(home=home),lane='local',inspect=lambda:{'state':'ready'}))
    monkeypatch.setattr(product_work,'open_work',lambda selected,name:WrapperFlow(context,home,'local'))
    primary=sqlite3.OperationalError('synthetic private primary')
    primary.sqlite_errorcode=9;primary.sqlite_errorname='SQLITE_INTERRUPT'
    primary.m1_reader_diagnostic={'phase':phase,'budget_ms':40 if phase=='snapshot_read' else 100,
                                 'elapsed_ms':41 if phase=='snapshot_read' else 101,'private':'must not publish'}
    def fail_before_admission(self,request):raise primary
    if phase=='snapshot_read':monkeypatch.setattr(CanonicalIntentReader,'read',fail_before_admission)
    else:monkeypatch.setattr(ReadOnly,'prepare',fail_before_admission)
    with pytest.raises(sqlite3.OperationalError) as caught:
        runpy.run_path(str(Path(__file__).parent.parent/'m1_v12_work.py'),run_name='__main__')
    assert caught.value is primary
    assert not any(call[1]=='POST' for call in context.calls)
    checkpoint=json.loads((tmp_path/'private/controller.json').read_text())
    assert checkpoint['requests']=={} and checkpoint['faults']==['CAMPAIGN_RUNNER_EXCEPTION']
    public=json.loads((tmp_path/'public/live-accounting.json').read_text())
    assert public['summary']['can_admit'] is False and public['summary']['current']==[]
    assert public['summary']['new_reserved_requests']==0
    error=json.loads((tmp_path/'public/m1v12-local-work-01-runner-error.json').read_text())
    assert error['error_type']=='OperationalError'
    assert error['reader_diagnostic']=={key:primary.m1_reader_diagnostic[key] for key in ('phase','budget_ms','elapsed_ms')}
    assert error['final_publication_diagnostics']['published_snapshots']==1
    assert 'synthetic private primary' not in json.dumps(error)
