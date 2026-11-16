"""Separate intact human-origin fixture: only canonical decision POST allowed."""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import uvicorn

HERE=Path(__file__).resolve().parent
ROOT=Path('D:\\Projetos\\Techridy\\okto_labs_okto_nexus')
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('ui04_human_base',HERE/'fixture.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


async def serve(s,args,home,preflight):
    requests=[]
    async def allowed(scope,receive,send):
        if scope['type']!='http':
            return await s.app(scope,receive,send)
        requests.append(dict(method=scope['method'],path=scope['path']))
        decision=scope['method']=='POST' and scope['path']=='/api/v1/runtime-management/runtime/approval-decisions'
        if scope['method'] not in {'GET','HEAD','OPTIONS'} and not decision:
            return await JSONResponse({'fixture':'Only exact canonical native decision POST allowed'},status_code=405)(scope,receive,send)
        # The human-origin proposal belongs to this disposable operator identity.
        role=dict(scope['headers']).get(b'x-ui04-fixture-actor',b'operator').decode()
        if role not in {'operator','subject','other'}:
            return await JSONResponse({'fixture':'invalid actor'},status_code=400)(scope,receive,send)
        headers=[(k,v) for k,v in scope['headers'] if k!=b'authorization']
        if role!='operator':headers.append((b'authorization',('Bearer '+s.app.state.test_agent_keys[role]).encode()))
        scope=dict(scope,headers=headers)
        return await s.app(scope,receive,send)
    static=ROOT/'src/okto_nexus/adapters/inbound/http/static'
    if args.expected_bundle not in (static/'index.html').read_text(encoding='utf-8'):
        raise RuntimeError('Frozen bundle changed; refusing start')
    server=uvicorn.Server(uvicorn.Config(allowed,host='127.0.0.1',port=0,lifespan='off',log_level='warning',timeout_graceful_shutdown=3))
    sock=server.config.bind_socket()
    files=[p for p in static.rglob('*') if p.is_file()]+[Path(__file__),HERE/'fixture.py',ROOT/'NEXUS_UI_R1/execution/fixtures.py',
        ROOT/'frontend/src/components/home/HomeEntryInspection.tsx',ROOT/'frontend/src/components/CanonicalNativeDecision.tsx']
    ready=dict(url=f'http://127.0.0.1:{sock.getsockname()[1]}',home=str(home),bundle=args.expected_bundle,
        original_session=s.sessions[0],closed_session=s.sessions[1],preflight=preflight,
        origin='intact base fixture; NO execution_domain_deliveries or runtime_handoff_binding added',
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    args.ready_file.write_text(json.dumps(ready,indent=2),encoding='utf-8')
    print(json.dumps({'url':ready['url'],'preflight':preflight}),flush=True)
    async def watch():
        end=asyncio.get_running_loop().time()+480
        while not server.should_exit:
            if args.stop_file.exists() or asyncio.get_running_loop().time()>end:
                server.should_exit=True
                return
            await asyncio.sleep(.2)
    task=asyncio.create_task(watch())
    try:
        await server.serve(sockets=[sock])
    finally:
        task.cancel();sock.close()
        with s.factory.unit_of_work(write=False) as uow:
            c=uow.connection
            summary=dict(
                input_operations=[dict(r) for r in c.execute("SELECT operation_id,action,actor_agent_id,subject_agent_id,session_id FROM execution_operations WHERE action='input.provide'")],
                matching_outbox=c.execute("SELECT COUNT(*) FROM delivery_outbox WHERE operation_id IN (SELECT operation_id FROM execution_operations WHERE action='input.provide')").fetchone()[0], decisions=c.execute('SELECT COUNT(*) FROM execution_decisions').fetchone()[0],
                decide_operations=c.execute("SELECT COUNT(*) FROM execution_operations WHERE action='approval.decide'").fetchone()[0],
                deliveries=c.execute('SELECT COUNT(*) FROM execution_domain_deliveries').fetchone()[0],
                stages=[r[0] for r in c.execute("SELECT r.stage FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id) WHERE o.action='approval.decide'")])
        args.ready_file.with_name('final-db.json').write_text(json.dumps(dict(summary=summary,requests=requests),indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--ready-file',type=Path,required=True);p.add_argument('--stop-file',type=Path,required=True);p.add_argument('--expected-bundle',required=True)
    args=p.parse_args()
    home=Path(tempfile.mkdtemp(prefix='nexus-ui04-human-'))
    with base.fixtures.scenario(home,recipient='operator',clock=base.fixtures.ControlledClock(datetime.now(timezone.utc).isoformat())) as s:
        preflight={}
        client=TestClient(s.app)
        try:
            for role in ('operator','subject','other'):
                r=client.get('/v1/runtime/input-requests',headers={'Authorization':'Bearer '+s.app.state.test_agent_keys[role]})
                preflight[role]=dict(status=r.status_code,items=len(r.json().get('items',[])))
        finally:client.close()
        assert preflight['operator']==dict(status=200,items=1),preflight
        assert preflight['subject']['items']==preflight['other']['items']==0
        asyncio.run(serve(s,args,home,preflight))
    print('CLOSED human fixture WSS/lifespan/factory',flush=True)


if __name__=='__main__':main()
