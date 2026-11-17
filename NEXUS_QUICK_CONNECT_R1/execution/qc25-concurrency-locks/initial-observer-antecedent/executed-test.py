"""Installed CLI, canonical HTTP/SQLite, real file locks; all harness peers inert."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier,get_ident
import time

import pytest
from types import SimpleNamespace
from test_quick_connect_cli import quick_cli,terminal,checking,local_setup,isolated_provider_environment
from test_connection_setup_recovery import snapshot
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock


def proof(name,value):
    (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/name).write_text(json.dumps(value,indent=2)+'\n')


def plan(c,capsys,profile):
    assert c.run(['connect','codex','App','--profile',profile,'--plan','--json'])==0
    value=json.loads(capsys.readouterr().out)
    assert value['state']=='review'
    return value


class ThreadOutput:
    def __init__(self,fallback):
        self.fallback=fallback
        self.buffers={}
    def write(self,text):
        buffer=self.buffers.get(get_ident())
        return (buffer if buffer is not None else self.fallback).write(text)
    def flush(self):
        buffer=self.buffers.get(get_ident())
        return (buffer if buffer is not None else self.fallback).flush()
    def isatty(self):
        return False


def test_c18_g15_two_initial_reviews_compete_at_canonical_reserve_only_one_finishes(quick_cli,monkeypatch,capsys):
    c=quick_cli
    a,b=plan(c,capsys,'race-a'),plan(c,capsys,'race-b')
    assert a['review_revision']!=b['review_revision']
    assert a['selection']['project']==b['selection']['project']==str(c.project)
    assert a['selection']['workspace_id'] is b['selection']['workspace_id'] is None
    assert c.t.turns==c.t.probes==[]
    barrier=Barrier(2)
    calls=[]
    original=c.t.call
    def canonical(method,path,body=None):
        if method=='POST' and path.endswith('/connections/public-ids/reserve'):
            calls.append((get_ident(),body['request']['client_intent_id']))
            barrier.wait(timeout=20)
        return original(method,path,body)
    monkeypatch.setattr(connect,'LocalOperatorHTTP',lambda **kwargs:canonical)
    stdout=ThreadOutput(sys.stdout)
    monkeypatch.setattr(sys,'stdout',stdout)
    def approve(profile,revision):
        buffer=io.StringIO()
        stdout.buffers[get_ident()]=buffer
        try:
            code=c.run(['connect','codex','App','--profile',profile,'--approve',revision,'--json','--no-chat'])
            return dict(profile=profile,code=code,value=json.loads(buffer.getvalue()))
        finally:
            stdout.buffers.pop(get_ident(),None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(approve,'race-a',a['review_revision']),pool.submit(approve,'race-b',b['review_revision'])]
        results=[future.result(timeout=45) for future in futures]
    assert sorted(r['code'] for r in results)==[0,3],results
    assert len(calls)==2 and len({intent for _,intent in calls})==2
    assert len(c.t.turns)==1
    winner=next(r for r in results if r['code']==0)
    loser=next(r for r in results if r['code']==3)
    saved=json.loads((c.home/'terminal/profiles'/(winner['profile']+'.json')).read_text())
    assert saved['state']=='done' and saved['result']['public_connection']['state']=='bound'
    reference=saved['result']['public_connection']['canonical_ref']
    counts={}
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('workspaces','connection_project_drafts','connection_public_ids','execution_bindings',
                      'runtime_execution_grants','connection_setup_commits'):
            counts[table]=uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
        assert set(counts.values())=={1},counts
        binding=dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
        grant=dict(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone())
        assert binding['binding_id']==reference['binding_id']
        assert binding['workspace_binding_id']==reference['workspace_binding_id']
        assert grant['workspace_id']==reference['workspace_id'] and grant['endpoint_id']==reference['endpoint_id']
        for table in ('execution_operations','execution_sessions'):
            assert uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    directory=original('GET','/api/v1/runtime-management/connections/workspaces')
    assert directory['total']==1 and directory['items'][0]['workspace_id']==reference['workspace_id']
    proof('race-proof.json',dict(counts=counts,tests=1,probes=len(c.t.probes),winner=winner['profile'],
        loser=loser['profile'],loser_code=loser['value'].get('code'),canonical_ref=reference,
        directory_recognizes_winner=True,barrier='Before actual canonical POST public-ids/reserve',
        thread_cwd_env_input_mutations=False))


def test_g12_profile_guard_busy_fails_fast_then_same_review_recovers(quick_cli,monkeypatch,capsys):
    c=quick_cli
    review=plan(c,capsys,'busy')
    profile=c.home/'terminal/profiles/busy.json'
    before_bytes=profile.read_bytes()
    before=snapshot(c.t.deps)
    guard=ExclusiveFileLock(c.home/'terminal/profiles/busy.guard')
    guard.acquire(create=False)
    started=time.monotonic()
    try:
        code=c.run(['connect','codex','App','--profile','busy','--plan','--json'])
        value=json.loads(capsys.readouterr().out)
        elapsed=time.monotonic()-started
        assert code==3 and value['code']=='PROFILE_BUSY'
        assert elapsed<5
        assert profile.read_bytes()==before_bytes and snapshot(c.t.deps)==before
        assert c.t.turns==c.t.probes==[]
    finally:
        guard.release()
    recovered=plan(c,capsys,'busy')
    assert recovered['review_revision']==review['review_revision']
    assert profile.read_bytes()==before_bytes and snapshot(c.t.deps)==before
    proof('busy-proof.json',dict(code='PROFILE_BUSY',elapsed_seconds=elapsed,within_five_seconds=True,
        same_review_after_release=True,profile_bytes_unchanged=True,authority_tables_unchanged=True,tests=0,probes=0))


PROBE='''
import importlib.util,json,os,pathlib,sys
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock
origins={name:importlib.util.find_spec(name).origin for name in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
assert all(pathlib.Path(value).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()) for value in origins.values())
results=[]
for value in json.loads(sys.argv[1]):
    lock=ExclusiveFileLock(pathlib.Path(value))
    lock.acquire(create=False)
    try: results.append(dict(path=value,acquired=True))
    finally: lock.release()
print(json.dumps(dict(pid=os.getpid(),prefix=sys.prefix,origins=origins,locks=results)))
'''


def test_g12_catalog_lock_free_during_input_and_old_profile_released_after_customize(quick_cli,monkeypatch,capsys):
    c=quick_cli
    monkeypatch.setattr(connect.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    probes=[]
    confirmations=[]
    old_guard=c.home/'terminal/profiles/old.guard'
    catalog=c.home/'terminal/connection-intents/catalog.guard'
    def probe(paths):
        command=[sys.executable,'-I','-B','-c',PROBE,json.dumps([str(path) for path in paths])]
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,cwd=c.project,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        process.stdin.close()
        process.stdin=None
        try:
            out,err=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
            pytest.fail('Owned lock probe exceeded five seconds',pytrace=False)
        assert process.returncode==0,err
        result=json.loads(out)
        result.update(launcher_pid=process.pid,exit_code=process.returncode,timeout_seconds=5)
        assert all(item['acquired'] for item in result['locks'])
        probes.append(result)
    def answer(prompt):
        if 'Confirm this review' in prompt:
            confirmations.append(prompt)
            assert c.t.turns==c.t.probes==[]
            if len(confirmations)==1:
                probe([catalog])
                return 'customize'
            assert len(confirmations)==2
            probe([catalog,old_guard])
            return 'n'
        if prompt=='Customize: ':
            probe([catalog])
            return '1'
        assert prompt=='New ID do Harness: '
        return 'reviewer'
    monkeypatch.setattr('builtins.input',answer)
    assert c.run(['connect','codex','App','--profile','old','--no-chat'])==0
    capsys.readouterr()
    old=json.loads((c.home/'terminal/profiles/old.json').read_text())
    assert old['state']=='superseded'
    new_profile=old['superseded_by_profile']
    new=json.loads((c.home/'terminal/profiles'/(new_profile+'.json')).read_text())
    assert new['state']=='review' and new['review_revision']!=old['review_revision']
    assert new['selection']['public_connection']['connect_id']=='reviewer'
    assert c.t.turns==c.t.probes==[]
    probe([catalog,old_guard,c.home/'terminal/profiles'/(new_profile+'.guard')])
    proof('input-lock-proof.json',dict(confirmations=2,customized_new_review=True,tests=0,probes=0,
        subprocesses=probes,old_profile_released_before_new_input=True,catalog_free_during_input=True))
