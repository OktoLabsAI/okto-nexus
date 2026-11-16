"""Own finite canonical heartbeat/lease renewal; no fresh-state SQL bypass."""
import argparse
import asyncio
from datetime import datetime,timezone
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

import pytest
from nexus_connector_core import encode_r4_frame,R4_PREVIEW_REVISION

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ui04_human_live_parent',HERE/'human-fixture.py')
human=importlib.util.module_from_spec(spec)
spec.loader.exec_module(human)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ready-file',type=Path,required=True);parser.add_argument('--stop-file',type=Path,required=True);parser.add_argument('--expected-bundle',required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(human.ROOT/'tests/execution_r4'))
    opening=importlib.import_module('test_open_bootstrap')
    leases_helper=importlib.import_module('test_session_capabilities')
    from okto_nexus.application import attention_native
    original=opening.opening.__wrapped__
    real_live=attention_native.require_live
    captured={};diagnostics=[];stop=threading.Event()
    def observed(*args,**kwargs):
        generator=original(*args,**kwargs)
        value=next(generator);captured['opening']=value
        try:yield value
        finally:generator.close()
    def diagnose(facts,now,policy):
        record=dict(kind='authority',now=now,wall=datetime.now(timezone.utc).isoformat(),
            lease=facts.get('latest_lease'),lane=facts.get('lane'))
        # Retain only explicit timing/state fields, never lane credential bytes.
        for key in ('lease','lane'):
            row=record[key] or {}
            record[key]={k:row[k] for k in ('status','last_seen_at','expires_at','ticket_expires_at','valid_until_server','lease_serial','connection_generation') if k in row}
        try:
            result=real_live(facts,now,policy);record['current']=True;return result
        except Exception as error:
            record.update(current=False,error=str(error),code=str(getattr(error,'code','')));raise
        finally:diagnostics.append(record)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(opening.opening,'__wrapped__',observed)
        patch.setattr(attention_native,'require_live',diagnose)
        home=Path(tempfile.mkdtemp(prefix='nexus-ui04-human-live-'))
        with human.base.fixtures.scenario(home,recipient='operator',clock=human.base.fixtures.ControlledClock(datetime.now(timezone.utc).isoformat())) as s:
            state=captured['opening'];channel=state[5];ws=s.app.state.test_opening_socket
            frame=dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='heartbeat',**channel.identity())
            def peer():
                end=time.monotonic()+180;last_renew=time.monotonic()
                while not stop.is_set() and time.monotonic()<end:
                    try:
                        ws.send_text(encode_r4_frame(frame).decode())
                        diagnostics.append(dict(kind='canonical_wss_heartbeat',wall=datetime.now(timezone.utc).isoformat()))
                        if time.monotonic()-last_renew>=30:
                            with s.factory.unit_of_work(write=False) as uow:
                                serial=uow.connection.execute('SELECT MAX(lease_serial) FROM execution_leases').fetchone()[0]
                            service,_,grant,ack=leases_helper.apply_lease(state,serial=serial,purpose='renew',request_id=f'ui04-renew-{serial}')
                            service.applied(ack,channel=channel)
                            diagnostics.append(dict(kind='canonical_lease_renewed',serial=grant['lease_serial'],valid_until_server=grant.get('valid_until_server')))
                            last_renew=time.monotonic()
                    except Exception as error:
                        diagnostics.append(dict(kind='peer_failed',error=str(error)));return
                    stop.wait(2)
            thread=threading.Thread(target=peer,name='own-ui04-canonical-peer',daemon=True);thread.start()
            preflight={}
            client=human.TestClient(s.app)
            try:
                for role in ('operator','subject','other'):
                    r=client.get('/v1/runtime/input-requests',headers={'Authorization':'Bearer '+s.app.state.test_agent_keys[role]})
                    preflight[role]=dict(status=r.status_code,items=len(r.json().get('items',[])))
            finally:client.close()
            try:asyncio.run(human.serve(s,args,home,preflight))
            finally:
                stop.set();thread.join(5)
                args.ready_file.with_name('liveness.json').write_text(json.dumps(dict(diagnostics=diagnostics,thread_stopped=not thread.is_alive(),limit_seconds=180),indent=2),encoding='utf-8')
    print('CLOSED canonical peer + WSS/lifespan/factory',flush=True)


if __name__=='__main__':main()
