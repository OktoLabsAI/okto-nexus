"""Offline mechanism probe, NOT a reproduction or diagnosis of historical M1v9."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
keep = {k:v for k,v in os.environ.items() if k.upper() in
        {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS'}}
for name in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP'):
    path=ROOT/'synthetic-home'/name.lower();path.mkdir(parents=True,exist_ok=True);keep[name]=str(path)
os.environ.clear();os.environ.update(keep)

import hashlib
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from okto_nexus.config import NexusConfig
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.adapters.outbound.sqlite.diagnostics import safe_db_diagnostic
from okto_nexus.bootstrap.embedded_agent_recovery import _diagnostic

EXPECTED=Path('C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/venv').resolve()
assert Path(sys.prefix).resolve()==EXPECTED
modules=['okto_nexus.config','okto_nexus.adapters.outbound.sqlite.connection',
         'okto_nexus.adapters.outbound.sqlite.execution_agent_revisions',
         'okto_nexus.adapters.outbound.sqlite.diagnostics',
         'okto_nexus.bootstrap.embedded_agent_recovery']
inputs={}
for name in modules:
    path=Path(sys.modules[name].__file__).resolve();assert path.is_relative_to(EXPECTED)
    inputs[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

factory=ConnectionFactory(NexusConfig(home_dir=ROOT/'synthetic-db',busy_timeout_ms=60,
                                    feature_harness_integrations=False))
schema=[
 'CREATE TABLE execution_installation(server_id TEXT,singleton INTEGER)',
 'CREATE TABLE agents(agent_id TEXT,is_active INTEGER,permissions TEXT,comm_scope TEXT,metadata TEXT,capabilities TEXT,api_key_hash TEXT)',
 'CREATE TABLE agent_connection_methods(agent_id TEXT,method TEXT)',
 'CREATE TABLE agent_endpoints(agent_id TEXT,endpoint_id TEXT,profile_id TEXT)',
 'CREATE TABLE runtime_profiles(profile_id TEXT)',
 'CREATE TABLE execution_agent_revisions(server_id TEXT,agent_id TEXT,authorization_revision INTEGER,configuration_revision INTEGER,credential_epoch INTEGER,authorization_digest TEXT,configuration_digest TEXT,credential_digest TEXT)',
]
with factory.unit_of_work() as uow:
    for sql in schema:uow.connection.execute(sql)
    uow.connection.execute("INSERT INTO execution_installation VALUES('synthetic_server',1)")
    uow.connection.execute("INSERT INTO agents VALUES('synthetic_agent',1,'{}','all','{}','{}',NULL)")

def refresh():return current_agent_revisions(factory,agent_id='synthetic_agent')

def failure():
    start=time.monotonic()
    try:refresh()
    except OktoNexusError as error:
        assert error.code=='DB_ERROR' and error.retryable is True
        return {'code':error.code,'elapsed_seconds':time.monotonic()-start,
                'safe_cause':safe_db_diagnostic(error),'recovery_diagnostic':_diagnostic(error)}
    raise AssertionError('Expected real contention refusal')

results={}
try:
    original=refresh()
    before=factory.unit_counts();again=refresh();after=factory.unit_counts()
    assert again==original and after[1]-before[1]==1
    results['unchanged_revision_still_requests_writer']={'passed':True,'write_units':1}
    with ThreadPoolExecutor(max_workers=1) as pool:
        with factory.unit_of_work() as holder:
            result=pool.submit(failure).result(timeout=3)
            assert result['safe_cause']=={'retryable':True,'writer_gate_timeout':True}
            assert holder.connection.in_transaction
            results['other_thread_same_factory_writer']=dict(result,passed=True)
            read=current_agent_revisions(factory,agent_id='synthetic_agent',persist=False)
            assert read==original
            results['readonly_revision_under_writer']={'passed':True,'same_revision':True}
        assert refresh()==original
    external=factory.get_connection()
    try:
        external.execute('BEGIN IMMEDIATE')
        result=failure()
        assert result['safe_cause']['sqlite_primary_errorcode']==sqlite3.SQLITE_BUSY
        assert result['safe_cause']['sqlite_errorname']=='SQLITE_BUSY'
        assert 'writer_gate_timeout' not in result['safe_cause']
        results['other_sqlite_connection_writer']=dict(result,passed=True)
    finally:external.close()
    assert refresh()==original
    results['post_release_recovery']={'passed':True,'same_revision':True}
finally:factory.close()

for value in inputs.values():assert hashlib.sha256(Path(value['path']).read_bytes()).hexdigest()==value['sha256']
report={'status':'PASS_MECHANISM_ONLY','cases':results,'imports':inputs,'python':sys.executable,
 'prefix':sys.prefix,'inputs_unchanged':True,'schema':'minimal synthetic schema for actual current_agent_revisions',
 'effects':{'HTTP':0,'provider':0,'service':0,'native_client':0,'credential_access':0},
 'limits':['Contention was deliberately injected, not observed in historical M1v9.',
           'This does not exercise full authorize_r4, tools issuance or a complete launch.',
           'No nested product transaction or HTTP-to-self deadlock was reproduced.',
           'The control uses persist=False only to characterize a read; it is not a proposed authorization patch.']}
(ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'passed':len(results),'result':str(ROOT/'result.json')}))
