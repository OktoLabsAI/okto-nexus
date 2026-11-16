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



def publish_question(s,state,index,view):
    from okto_nexus.application.execution_events import commit_execution_events
    channel=state[5];scope=state[6]['scope']
    with s.factory.unit_of_work(write=False) as uow:
        operation=uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit' ORDER BY created_at LIMIT 1").fetchone()[0]
        before=uow.connection.execute("SELECT COUNT(*) FROM approvals WHERE action='execution.native.respond'").fetchone()[0]
    proposal=dict(schema_version=1,request_id=7+index,request_hash=str(index)*64,
        method='item/tool/requestUserInput',params=dict(turnId='native-turn',itemId='nav-'+view,
        isBlocking=True,questions=[dict(id='nav-question-'+view,header='New '+view,
        question='New question while viewing '+view,isOther=True,
        options=[dict(label='Continue',description='Synthetic inert choice'),dict(label='Stop',description='Synthetic stop')])]))
    event=dict(server_id=channel.server_id,executor_id=channel.executor_id,session_id=scope['session_id'],
        stream_epoch='native-epoch',sequence=index+1,category='input_request',operation_id=operation,
        payload=dict(native_approval=proposal,native_approval_display=proposal))
    frame={key:scope[key] for key in ('server_id','executor_id','binding_id','agent_id','session_id')}
    frame.update(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='event.batch',
        connection_id=channel.connection_id,connection_generation=channel.connection_generation,
        stream_epoch='native-epoch',events=[event])
    commit_execution_events(s.factory,channel=channel,frame=frame,approvals=s.deps.approvals)
    with s.factory.unit_of_work(write=False) as uow:
        rows=uow.connection.execute("SELECT approval_id,request_payload FROM approvals WHERE action='execution.native.respond'").fetchall()
        found=[dict(approval_id=row['approval_id']) for row in rows if 'New question while viewing '+view in row['request_payload']]
    assert len(rows)==before+1 and len(found)==1
    # Publish only canonical public identity; no nonce, bearer or request payload.
    question_publication[view]=dict(before=before,after=len(rows),**found[0])

question_publication={}

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
            s.deps.config.feature_memory=False
            state=captured['opening'];channel=state[5];ws=s.app.state.test_opening_socket
            frame=dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='heartbeat',**channel.identity())
            def peer():
                end=time.monotonic()+300;last_renew=time.monotonic();published=set()
                while not stop.is_set() and time.monotonic()<end:
                    try:
                        ws.send_text(encode_r4_frame(frame).decode())
                        for index,view in enumerate(('Graph','Artifacts'),start=1):
                            trigger=args.ready_file.with_name('trigger-'+view)
                            if trigger.exists() and view not in published:
                                publish_question(s,state,index,view)
                                args.ready_file.with_name('arrival-'+view+'.json').write_text(json.dumps(question_publication[view]),encoding='utf8')
                                published.add(view)
                                diagnostics.append(dict(kind='canonical_new_question',view=view))
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
