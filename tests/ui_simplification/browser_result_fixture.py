"""Canonical read projections over own explicit historical facts, no provider.

Allows only exact canonical attention viewing-preference writes. Native and
business execution is not simulated by HTTP DTOs or acknowledged on viewing.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

from fastapi.responses import JSONResponse
import uvicorn

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('result_browser_base',ROOT/'NEXUS_UI_R1/execution/evidence/pr04-browser/fixture.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def snapshot(s):
    tables=('handoffs','message_deliveries','execution_operations','execution_receipts',
            'execution_event_watermarks','attention_preferences')
    with s.factory.unit_of_work(write=False) as uow:
        return {table:dict(count=len(rows),sha256=hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest())
                for table in tables for rows in [[list(r) for r in uow.connection.execute('SELECT * FROM '+table+' ORDER BY rowid')]]}


def seed(s):
    from tests.ui_simplification.test_entry_relations import link_handoff
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    now=s.clock.now_iso();old=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    with s.factory.unit_of_work() as uow:
        c=uow.connection;link_handoff(c,now)
        c.execute("UPDATE handoffs SET status='VERIFYING',claimed_by='B',verify_by=?,result='Synthetic three-file delivery' WHERE handoff_id='ui-handoff-0'",(json.dumps({'kind':'agent','agent_id':'operator'}),))
        c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,'ui-success','entry-domain')",(s.connections[0].server_id,s.connections[0].executor_id))
        operation=c.execute("SELECT * FROM execution_operations WHERE operation_id='ui-success'").fetchone()
        # Stored historical results, explicitly not claims of native execution.
        for i,op in enumerate(('ui-success','ui-old-unseen','ui-untracked','ui-hidden-0','ui-hidden-1','ui-hidden-2')):
            if op!='ui-success':
                base.fixtures._copy(c,'execution_operations',operation,operation_id=op)
                c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,?,1,?,'SUCCEEDED',1,0,?)",(s.connections[0].server_id,s.connections[0].executor_id,op,operation['intent_hash'],old if op=='ui-old-unseen' else now))
            if op!='ui-untracked':
                c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','ui-historical-epoch',?,?,'turn.completed','{}',?)",(s.connections[0].server_id,s.connections[0].executor_id,10+i,'result-event-'+str(i),old if op=='ui-old-unseen' else now))
                c.execute("INSERT INTO execution_results VALUES(?,?,?,'ui-session-2','ui-historical-epoch',?,?,0,1,'success',?)",(s.connections[0].server_id,s.connections[0].executor_id,op,10+i,'Synthetic '+op,old if op=='ui-old-unseen' else now))
        workspace=c.execute("SELECT * FROM workspaces WHERE workspace_id='ws'").fetchone()
        base.fixtures._copy(c,'workspaces',workspace,workspace_id='ui-outside-workspace',root_realpath=str(Path(s.deps.config.home_dir)/'outside-project'))
        handoff=c.execute("SELECT * FROM handoffs WHERE handoff_id='ui-handoff-1'").fetchone()
        base.fixtures._copy(c,'handoffs',handoff,handoff_id='ui-outside-result',workspace_id='ui-outside-workspace',status='COMPLETED',result='Outside selected project',claim_epoch=1)
    artifacts=[]
    for i in range(3):
        a=build_service(s.deps).artifact_upload(workspace_id='ws',filename='delivery-'+str(i)+'.txt',data=('Synthetic file '+str(i)).encode(),media_type='text/plain',agent_id='operator')
        artifacts.append(a['artifact_id'])
        with s.factory.unit_of_work() as uow:
            c=uow.connection;op='ui-success' if i==0 else 'ui-file-op-'+str(i)
            if i:
                base.fixtures._copy(c,'execution_operations',operation,operation_id=op)
                c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,?,1,?,'SUCCEEDED',1,0,?)",(s.connections[0].server_id,s.connections[0].executor_id,op,operation['intent_hash'],now))
                c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,?,'entry-domain')",(s.connections[0].server_id,s.connections[0].executor_id,op))
                c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','ui-historical-epoch',?,?,'turn.completed','{}',?)",(s.connections[0].server_id,s.connections[0].executor_id,30+i,'file-event-'+str(i),now))
                c.execute("INSERT INTO execution_results VALUES(?,?,?,'ui-session-2','ui-historical-epoch',?,?,0,1,'success',?)",(s.connections[0].server_id,s.connections[0].executor_id,op,30+i,'Synthetic file-producing operation',now))
            c.execute("INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES(?,'{}',?,'entry-domain',?,?,?,?)",('ui-file-result-'+str(i),now,s.connections[0].server_id,s.connections[0].executor_id,op,a['artifact_id']))
    return dict(artifacts=artifacts,verifying_handoff='ui-handoff-0',old_operation='ui-old-unseen',outside_handoff='ui-outside-result')


async def serve(s,args,home,identities):
    requests=[];checkpoints={}
    async def allowed(scope,receive,send):
        if scope['type']=='http':
            requests.append(dict(method=scope['method'],path=scope['path']))
            preference=scope['method']=='POST' and scope['path'].startswith('/api/v1/attention/') and scope['path'].endswith(('/seen','/unseen'))
            if scope['method'] not in {'GET','HEAD','OPTIONS'} and not preference:
                return await JSONResponse({'fixture':'Only own canonical viewing-preference mutation allowed'},status_code=405)(scope,receive,send)
        return await s.app(scope,receive,send)
    static=ROOT/'src/okto_nexus/adapters/inbound/http/static'
    assert args.expected_bundle in (static/'index.html').read_text()
    server=uvicorn.Server(uvicorn.Config(allowed,host='127.0.0.1',port=0,lifespan='off',log_level='warning',timeout_graceful_shutdown=3))
    sock=server.config.bind_socket()
    ready=dict(url='http://127.0.0.1:'+str(sock.getsockname()[1]),home=str(home),identities=identities,
        snapshot=snapshot(s),source_sha256={str(p.resolve().relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'src/okto_nexus/adapters/outbound/sqlite/home.py',static/'index.html',static/'assets'/args.expected_bundle]})
    args.ready_file.write_text(json.dumps(ready,indent=2),encoding='utf8')
    async def watch():
        end=asyncio.get_running_loop().time()+600
        while not server.should_exit:
            for name in ('after-read','after-seen'):
                if args.ready_file.with_name('capture-'+name).exists() and name not in checkpoints:
                    checkpoints[name]=snapshot(s)
                    args.ready_file.with_name(name+'.json').write_text(json.dumps(checkpoints[name],indent=2),encoding='utf8')
            if args.stop_file.exists() or asyncio.get_running_loop().time()>end:server.should_exit=True
            await asyncio.sleep(.2)
    task=asyncio.create_task(watch())
    try:await server.serve(sockets=[sock])
    finally:
        task.cancel();sock.close()
        args.ready_file.with_name('final-db.json').write_text(json.dumps(dict(snapshot=snapshot(s),requests=requests),indent=2),encoding='utf8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--ready-file',type=Path,required=True);p.add_argument('--stop-file',type=Path,required=True);p.add_argument('--expected-bundle',required=True);args=p.parse_args()
    home=Path(tempfile.mkdtemp(prefix='nexus-ui-results-browser-'))
    args.ready_file.with_name('allocation.json').write_text(json.dumps({'home':str(home)}),encoding='utf8')
    with base.fixtures.scenario(home,clock=base.fixtures.ControlledClock(datetime.now(timezone.utc).isoformat())) as s:
        identities=seed(s)
        asyncio.run(serve(s,args,home,identities))
    print('CLOSED own result fixture WSS/lifespan/factory',flush=True)


if __name__=='__main__':main()
