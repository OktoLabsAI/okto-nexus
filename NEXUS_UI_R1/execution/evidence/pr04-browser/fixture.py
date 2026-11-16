"""Finite own real-GET UI028/034/041 fixture; no provider/native process.

UI data comes from the shared admitted scenario plus explicit synthetic read
facts. This is not an execution campaign. Test-only header selects which real
fixture credential reaches canonical HTTP authorization. No responses/DTOs are
fulfilled or rewritten. All POST/PUT/PATCH/DELETE are rejected before handlers.
"""
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
import uvicorn

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
spec = importlib.util.spec_from_file_location('ui04_fixture',ROOT/'NEXUS_UI_R1/execution/fixtures.py')
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name]=fixtures
spec.loader.exec_module(fixtures)
from tests.ui_simplification.test_entry_relations import copy_session,link_handoff


def seed(s):
    with s.factory.unit_of_work() as uow:
        c,now=uow.connection,s.clock.now_iso()
        link_handoff(c,now)
        original=c.execute('SELECT * FROM execution_sessions WHERE session_id=?',(s.sessions[0],)).fetchone()
        turn=c.execute("SELECT * FROM execution_operations WHERE action='turn.submit' AND binding_id='binding'").fetchone()
        copy_session(c,original,'ui04-second-exact-session')
        copy_session(c,original,'ui04-no-turn-session')
        # Explicit empty retained streams for these own synthetic sessions.
        # A copied non-null epoch without its watermark is canonically404,
        # rather than an empty successfully recorded history.
        for sid in ('ui04-second-exact-session','ui04-no-turn-session'):
            c.execute("INSERT INTO execution_event_watermarks VALUES(?,?,?,?,0,0,'none')",
                (original['server_id'],original['executor_id'],sid,original['stream_epoch']))
        scope=dict(json.loads(turn['expected_revisions_json']),session_id='ui04-second-exact-session')
        fixtures._copy(c,'execution_operations',turn,operation_id='ui04-second-linked-turn',
            session_id='ui04-second-exact-session',expected_revisions_json=json.dumps(scope))
        for oid in (turn['operation_id'],'ui04-second-linked-turn'):
            c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,?,'entry-domain')",
                (turn['server_id'],turn['executor_id'],oid))
    return dict(original_session=s.sessions[0],second_session='ui04-second-exact-session',
        no_turn_session='ui04-no-turn-session',multi_session_source='ui-handoff-0',
        closed_session=s.sessions[1],synthetic_additions=True)


async def serve(s,args,home,identities):
    requests=[]
    async def own_read_only(scope,receive,send):
        if scope['type']!='http':
            return await s.app(scope,receive,send)
        requests.append(dict(method=scope['method'],path=scope['path']))
        if scope['method'] not in {'GET','HEAD','OPTIONS'}:
            return await JSONResponse({'fixture':'read-only qualification; canonical mutation not invoked'},status_code=405)(scope,receive,send)
        role=dict(scope['headers']).get(b'x-ui04-fixture-actor',b'operator').decode()
        if role not in {'operator','subject','other'}:
            return await JSONResponse({'fixture':'invalid fixture actor'},status_code=400)(scope,receive,send)
        headers=[(k,v) for k,v in scope['headers'] if k!=b'authorization']
        if role!='operator':
            key=s.app.state.test_agent_keys[role]
            headers.append((b'authorization',('Bearer '+key).encode()))
        scope=dict(scope,headers=headers)
        return await s.app(scope,receive,send)
    config=uvicorn.Config(own_read_only,host='127.0.0.1',port=0,lifespan='off',log_level='warning',timeout_graceful_shutdown=3)
    server=uvicorn.Server(config)
    sock=config.bind_socket()
    paths=['frontend/src/components/home/HomeInspection.tsx','frontend/src/components/home/HomeEntryInspection.tsx',
        'frontend/src/components/home/HomeSessionInspection.tsx','frontend/src/components/AgentActionModal.tsx',
        'frontend/src/components/home/OperationalHome.tsx','frontend/src/components/home/HomeCards.tsx',
        'frontend/src/homeController.ts','frontend/src/homeEntryInspection.ts','frontend/src/components/RuntimeOperations.tsx',
        'src/okto_nexus/application/home_entries.py','src/okto_nexus/domain/home_entry_pages.py',
        'src/okto_nexus/adapters/outbound/sqlite/home_entries.py','NEXUS_UI_R1/execution/fixtures.py',
        str(Path(__file__).relative_to(ROOT)).replace('\\','/')]
    static=ROOT/'src/okto_nexus/adapters/inbound/http/static'
    files=[ROOT/p for p in paths]+[p for p in static.rglob('*') if p.is_file()]
    pins={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    ready=dict(url=f'http://127.0.0.1:{sock.getsockname()[1]}',home=str(home),
        identities=identities,source_sha256=pins,synthetic=True,read_only=True,
        static_build_verified_by_root=args.expected_bundle,
        app_lifespan='off; shared fixture owns its admitted mock WSS lifecycle',
        personal_auth=False,provider=False,native_binary=False)
    actual_html=(static/'index.html').read_text(encoding='utf-8')
    if args.expected_bundle not in actual_html:
        sock.close()
        raise RuntimeError('Expected frozen bundle not in static/index.html; refusing stale cut')
    async def watch():
        deadline=asyncio.get_running_loop().time()+args.duration
        while not server.should_exit:
            if args.stop_file.exists() or asyncio.get_running_loop().time()>=deadline:
                server.should_exit=True
                return
            await asyncio.sleep(.2)
    task=asyncio.create_task(watch())
    args.ready_file.write_text(json.dumps(ready,indent=2),encoding='utf-8')
    print(json.dumps(dict(url=ready['url'],ready_file=str(args.ready_file))),flush=True)
    try:
        await server.serve(sockets=[sock])
    finally:
        task.cancel()
        sock.close()
        args.ready_file.with_name('fixture-requests.json').write_text(json.dumps(requests,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stop-file',type=Path,required=True)
    parser.add_argument('--ready-file',type=Path,required=True)
    parser.add_argument('--expected-bundle',required=True)
    parser.add_argument('--duration',type=int,default=360)
    args=parser.parse_args()
    if not 30<=args.duration<=600:
        parser.error('duration must be 30..600 seconds')
    home=Path(tempfile.mkdtemp(prefix='nexus-ui04-browser-'))
    with fixtures.scenario(home,clock=fixtures.ControlledClock(datetime.now(timezone.utc).isoformat())) as s:
        identities=seed(s)
        asyncio.run(serve(s,args,home,identities))
    print('CLOSED: shared WSS/lifespan and factory exited normally',flush=True)


if __name__=='__main__':
    main()
