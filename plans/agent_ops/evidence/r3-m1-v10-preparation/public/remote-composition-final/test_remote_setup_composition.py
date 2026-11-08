"""Actual remote wrapper and monitor with synthetic callbacks, no external effects."""
import json
from pathlib import Path
import runpy
import sys
import threading
import time
import types

import pytest


@pytest.mark.parametrize('mode',['normal','late_start','unknown_job','existing_stop','setup_only_fault','local_spawn_failure'])
def test_remote_wrapper_defers_both_stops_until_owned_helper_drains(tmp_path,monkeypatch,mode):
    root=tmp_path/'synthetic-campaign';root.mkdir()
    for name in ('public','private','nexus-home','connector-state','operator-home'):(root/name).mkdir()
    owner=threading.get_ident();events=[];consumer=threading.Event();produced=[]
    class Control:
        def __init__(self):self.closed=False;self.stops={};self.faults=[];self.fence=self;self.data={'requests':{}}
        def attach_owner(self,lane,home,stop):
            assert threading.get_ident()==owner
            self.stops[lane]=stop;events.append('attach-'+lane)
        def fault(self,code):
            assert threading.get_ident()==owner
            self.closed=True;self.faults.append(code)
        def poll(self):
            assert threading.get_ident()==owner
            if mode in ('late_start','unknown_job','existing_stop','local_spawn_failure') and consumer.is_set():self.fault('SYNTHETIC_LATE_USAGE')
            if mode=='setup_only_fault' and 'ready' in events:self.fault('SYNTHETIC_SETUP_LATE_USAGE')
            if self.closed:self.stops['local']()  # No Connector work record exists.
            return {'can_admit':not self.closed,'current':None}
        def arm(self,deadline):
            assert not self.closed
        def require(self,verb):
            if self.closed:raise RuntimeError('FENCED')
        def close(self):events.append('controller-closed')
    control=Control()
    profile='m1v10-connector';profile_file=root/'operator-home/terminal/profiles'/f'{profile}.json'
    profile_file.parent.mkdir(parents=True)
    doc={'kind':'remote_project_setup','state':'review','review_revision':'r1','server_id':'server',
         'remote_review':{'review_revision':'r1','draft':{'server_origin':'http://127.0.0.1:1',
          'setup_run_id':'m1v10-connector-setup','installation':{'candidate_ref':'candidate'},'start_at_login':False}}}
    profile_file.write_text(json.dumps(doc))
    (root/'public/remote-review-selection.json').write_text(json.dumps({'proposal_sha256':'a'*64,
        'review_revision':'r1','server_id':'server','profile':profile}))
    helper=tmp_path/'synthetic_helper.py';helper.write_text('from synthetic_remote_helper import transfer_once\n')
    P={'execution_bundle':{'profiles':{'connector':profile},'operator_profile':'synthetic',
        'files':{'protected_pty':{'path':str(helper)}}},
        'paths':{'server_home':str(root/'nexus-home'),'connector_state':str(root/'connector-state'),'operator_home':str(root/'operator-home')},
        'native_selection':{'candidate_ref':'candidate'},'package_pins':{'python':'synthetic-python'}}
    context=types.SimpleNamespace(P=P,C={'origin':'http://127.0.0.1:1'},ROOT=root,
        modules=Path(__file__).parent/'controller',remaining=['transfer'],
        args=types.SimpleNamespace(expected_proposal_sha256='a'*64),controller=lambda:control,
        env=lambda:{},stop_argv=lambda component:['synthetic-stop',component])
    ctx=types.ModuleType('campaign_context');ctx.load=lambda:context
    def require(value,code):
        if not value:raise RuntimeError(code)
    ctx.require=require
    def reserve(path,value):
        assert threading.get_ident()==owner
        with path.open('x') as stream:json.dump(value,stream)
    ctx.reserve_json=reserve;monkeypatch.setitem(sys.modules,'campaign_context',ctx)
    pub=types.ModuleType('publication');pub.poll_and_publish=lambda c,*args:c.poll();monkeypatch.setitem(sys.modules,'publication',pub)
    hist=types.ModuleType('history_observers')
    def attach(c,**kwargs):
        assert 'local' in c.stops;return []  # Setup-only history, no work lanes.
    hist.attach_existing_work=attach;monkeypatch.setitem(sys.modules,'history_observers',hist)
    supervisor=types.ModuleType('supervisor_check')
    def observe(x):
        events.append('ready');return {'instance_id':'instance','task_name':'task','task_digest':'digest','generation':'g','pid':900}
    supervisor.observe_connector=observe;monkeypatch.setitem(sys.modules,'supervisor_check',supervisor)
    synthetic=types.ModuleType('synthetic_remote_helper')
    def transfer_once(**kw):
        assert threading.get_ident()!=owner
        produced.append('once')
        assert kw['effect_guard']('producer')
        assert kw['effect_guard']('consumer')
        consumer.set()
        if mode!='normal':
            limit=time.monotonic()+2
            while not control.closed and time.monotonic()<limit:time.sleep(.001)
            assert control.closed
            assert not any(e.startswith('stop-') for e in events)
            events.append('implicit-start-completed-late')
        else:
            profile_file.write_text(json.dumps(dict(doc,state='done')))
        events.append('job-empty' if mode!='unknown_job' else 'job-unknown')
        return {'status':'TRANSFERRED_ONCE','producer_exit':0,'consumer_exit':0,
            'worker_exit':0,'worker_assigned_before_gate':True,
            'active_job_processes_after':None if mode=='unknown_job' else 0,
            'forced_owned_cleanup':False,'effect_guard_required':True,
            'effect_gates_allowed':['producer','consumer'],'public_ipc_readers_joined':True}
    synthetic.transfer_once=transfer_once;monkeypatch.setitem(sys.modules,'synthetic_remote_helper',synthetic)
    import subprocess
    class Child:
        def __init__(self,argv,**kw):
            assert threading.get_ident()==owner
            assert 'job-empty' in events
            lane=argv[-1];events.append('stop-'+lane)
            # Durable phase DISPATCH_RESERVED precedes every fake Popen.
            snapshots=[json.loads(p.read_text()) for p in (root/'public').glob('remote-stop-order-*.json')]
            selected='local' if lane=='nexus' else 'connector'
            assert any(s['stops'].get(selected,{}).get('state')=='DISPATCH_RESERVED' for s in snapshots)
            if mode=='local_spawn_failure' and lane=='nexus':raise OSError('synthetic Popen failure')
            self.pid=101;self.returncode=0
        def poll(self):return 0
    monkeypatch.setattr(subprocess,'Popen',Child)
    if mode=='existing_stop':(root/'public/lifecycle-nexus-stop.json').write_text('{"state":"DISPATCH_RESERVED"}')
    if mode=='normal':runpy.run_path(str(Path(__file__).parent/'m1_v10_remote_setup.py'),run_name='__main__')
    else:
        with pytest.raises(SystemExit) as e:runpy.run_path(str(Path(__file__).parent/'m1_v10_remote_setup.py'),run_name='__main__')
        assert e.value.code==3
    stops=[v for v in events if v.startswith('stop-')]
    if mode in ('normal','unknown_job','setup_only_fault'):assert stops==[]
    elif mode=='existing_stop':assert stops==['stop-connector']
    else:assert stops==['stop-nexus','stop-connector']
    if stops:assert events.index('implicit-start-completed-late')<events.index('job-empty')<min(events.index(s) for s in stops)
    if mode=='setup_only_fault':assert produced==[]
    else:assert produced==['once']
    latest=sorted((root/'public').glob('remote-stop-order-*.json'))[-1]
    audit=json.loads(latest.read_text())
    assert audit['service_exit_confirmed'] is False
    if mode!='normal':assert set(audit['stops'])=={'local','connector'}
    if mode=='unknown_job':assert audit['drain_basis']=='HELPER_JOB_UNCONFIRMED'
    if mode=='local_spawn_failure':
        assert audit['stops']['local']['state']=='DISPATCH_UNCONFIRMED'
        assert audit['stops']['local']['error_type']=='OSError'
        assert audit['stops']['connector']['state']=='WRAPPER_STARTED'
    assert 'controller-closed' in events
