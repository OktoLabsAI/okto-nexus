"""Own canonical native question, finite maintenance, no provider or login reuse."""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time

import pytest
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from nexus_connector_core import encode_r4_frame,R4_PREVIEW_REVISION

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('attention_authority_base',ROOT/'NEXUS_UI_R1/execution/evidence/pr04-browser/fixture.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


class WallClock:
    def now_iso(self):return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
    def now_epoch(self):return time.time()


def state(s):
    with s.factory.unit_of_work(write=False) as uow:
        c=uow.connection
        return dict(decisions=c.execute('SELECT COUNT(*) FROM execution_decisions').fetchone()[0],
            inputs=c.execute("SELECT COUNT(*) FROM execution_operations WHERE action='input.provide'").fetchone()[0],
            input_outbox=c.execute("SELECT COUNT(*) FROM execution_dispatch_outbox WHERE operation_id IN (SELECT operation_id FROM execution_operations WHERE action='input.provide')").fetchone()[0],
            native_requests=[dict(r) for r in c.execute('SELECT canonical_request_id,state,received_at,expires_at FROM execution_native_requests')],
            grants=[dict(r) for r in c.execute('SELECT grant_id,expires_at,max_executions,used_executions FROM runtime_execution_grants')])


async def serve(s,args,home,stop,diagnostics):
    requests=[]
    async def app(scope,receive,send):
        if scope['type']!='http':return await s.app(scope,receive,send)
        path=scope['path'];method=scope['method']
        if any(k==b'authorization' for k,v in scope['headers']):
            return await JSONResponse({'fixture':'Only canonical human loopback authority in browser'},status_code=403)(scope,receive,send)
        if method not in {'GET','HEAD','OPTIONS'} and not(method=='POST' and path=='/api/v1/runtime-management/runtime/approval-decisions'):
            return await JSONResponse({'fixture':'Only one own canonical native decision attempt allowed'},status_code=405)(scope,receive,send)
        async def logged(message):
            if message['type']=='http.response.start':requests.append(dict(method=method,path=path,status=message['status']))
            await send(message)
        return await s.app(scope,receive,logged)
    static=ROOT/'src/okto_nexus/adapters/inbound/http/static'
    assert args.expected_bundle in (static/'index.html').read_text()
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=0,lifespan='off',log_level='warning',timeout_graceful_shutdown=3));sock=server.config.bind_socket()
    ready=dict(url='http://127.0.0.1:'+str(sock.getsockname()[1]),home=str(home),recipient=args.recipient,
        approval_id=s.decision_body['approval_key']['canonical_request_id'],server_id=s.connections[0].server_id,
        home_off=args.home_off,initial_state=state(s),request_expiry_unchanged=True,
        source_sha256={str(p.resolve().relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),static/'index.html',static/'assets'/args.expected_bundle)})
    args.ready_file.write_text(json.dumps(ready,indent=2),encoding='utf8');print(json.dumps({'READY':ready['url']}),flush=True)
    async def watch():
        end=time.monotonic()+180
        while not server.should_exit:
            if args.stop_file.exists() or time.monotonic()>end:server.should_exit=True
            await asyncio.sleep(.2)
    task=asyncio.create_task(watch())
    try:await server.serve(sockets=[sock])
    finally:
        task.cancel();sock.close();stop.set()
        args.ready_file.with_name('final-db.json').write_text(json.dumps(dict(state=state(s),requests=requests),indent=2),encoding='utf8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--ready-file',type=Path,required=True);p.add_argument('--stop-file',type=Path,required=True);p.add_argument('--expected-bundle',required=True);p.add_argument('--recipient',choices=('subject','operator'),required=True);p.add_argument('--home-off',action='store_true');args=p.parse_args()
    opening=importlib.import_module('test_open_bootstrap');leases=importlib.import_module('test_session_capabilities');original=opening.opening.__wrapped__;captured={};stop=threading.Event();diagnostics=[]
    def capture(*a,**kw):
        gen=original(*a,**kw);opened=next(gen);captured['state']=opened
        try:yield opened
        finally:gen.close()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(opening.opening,'__wrapped__',capture)
        home=Path(tempfile.mkdtemp(prefix='nexus-ui-attention-authority-'))
        args.ready_file.with_name('allocation.json').write_text(json.dumps({'home':str(home)}),encoding='utf8')
        with base.fixtures.scenario(home,recipient=args.recipient,clock=WallClock()) as s:
            opened=captured['state'];channel=opened[5];ws=s.app.state.test_opening_socket
            from ns14_load import refresh_inventory
            client=TestClient(s.app,base_url='https://127.0.0.1:8202')
            def peer():
                inventory=0;renew=time.monotonic()
                while not stop.wait(2):
                    try:
                        ws.send_text(encode_r4_frame(dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='heartbeat',**channel.identity())).decode())
                        if time.monotonic()-inventory>=30:
                            refresh_inventory(opened,home,client);inventory=time.monotonic();diagnostics.append({'kind':'canonical_inventory_put'})
                        if time.monotonic()-renew>=15:
                            with s.factory.unit_of_work(write=False) as uow:serial=uow.connection.execute('SELECT MAX(lease_serial) FROM execution_leases').fetchone()[0]
                            service,_,grant,ack=leases.apply_lease(opened,serial=serial,purpose='renew',request_id='authority-renew-'+str(serial));service.applied(ack,channel=channel);renew=time.monotonic();diagnostics.append({'kind':'canonical_lease_applied','serial':grant['lease_serial']})
                    except Exception as error:diagnostics.append({'kind':'peer_failed','error':str(error)});return
            thread=threading.Thread(target=peer,name='own-attention-inert-peer',daemon=True);thread.start()
            try:asyncio.run(serve(s,args,home,stop,diagnostics))
            finally:stop.set();thread.join(5);client.close()
    args.ready_file.with_name('maintenance.json').write_text(json.dumps(dict(diagnostics=diagnostics,thread_stopped=not thread.is_alive()),indent=2),encoding='utf8')
    print('CLOSED own attention peer/WSS/factory',flush=True)


if __name__=='__main__':main()
