import base64
import json
import pytest
from nexus_connector_core.event_artifacts import externalize_event, artifact_chunks, event_reference
from okto_nexus.application.execution_event_artifacts import resolve_event, ExecutionEventArtifacts
from test_event_ingress import ingress, commit
from test_reconciliation import recovery
from test_binding_operator import onboarding
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


def large(ingress,size=95000):
    factory,channel,frame=ingress
    original=dict(frame['events'][0],payload={'output_text':'é🙂'*(size//6)})
    wire,raw=externalize_event(original)
    base={k:v for k,v in frame.items() if k not in ('events','session_id','stream_epoch','type')}
    return original,wire,list(artifact_chunks(base,wire,raw))


@pytest.mark.parametrize('size',[70000,95000,2*1024*1024])
def test_store_before_ack_replay_and_integrity(ingress,size):
    factory,channel,frame=ingress
    original,wire,chunks=large(ingress,size)
    with pytest.raises(ValueError,match='durably'):
        commit(ingress,dict(frame,events=[wire]))
    for chunk in reversed(chunks):
        factory.event_artifacts.receive(chunk,channel=channel)
    assert commit(ingress,dict(frame,events=[wire]))['sequence']==1
    # Recreate the service (restart), resend chunks after a lost ACK, and replay.
    factory.event_artifacts=ExecutionEventArtifacts(factory,factory.event_artifacts.store)
    for chunk in chunks: factory.event_artifacts.receive(chunk,channel=channel)
    assert commit(ingress,dict(frame,events=[wire]))['sequence']==1
    assert commit(ingress,dict(frame,events=[dict(frame['events'][0],sequence=2)]))['sequence']==2
    with factory.unit_of_work(write=False) as uow:
        assert resolve_event(factory,uow.connection,wire)==original
        saved=uow.connection.execute('SELECT payload_json FROM execution_event_ingress WHERE sequence=1').fetchone()[0]
        assert len(saved.encode())<65536 and event_reference(json.loads(saved))
        assert uow.connection.execute('SELECT count(*) FROM execution_event_artifact_chunks').fetchone()[0]==0


def test_chunk_conflicts_and_foreign_authority(ingress):
    factory,channel,_=ingress
    _,wire,chunks=large(ingress)
    factory.event_artifacts.receive(chunks[0],channel=channel)
    bad=dict(chunks[0],data=base64.b64encode(b'x'*32768).decode())
    with pytest.raises(ValueError,match='conflict'): factory.event_artifacts.receive(bad,channel=channel)
    with pytest.raises(ValueError,match='authorized'): factory.event_artifacts.receive(dict(chunks[0],agent_id='other'),channel=channel)
    with factory.unit_of_work(write=False) as uow:
        with pytest.raises(ValueError,match='durably'): resolve_event(factory,uow.connection,wire)


def test_store_failure_keeps_replay_and_quota_is_reported(ingress,monkeypatch):
    from okto_nexus.errors import OktoNexusError
    factory,channel,frame=ingress
    _,wire,chunks=large(ingress)
    store=factory.event_artifacts.store
    original=store.put
    def fail(**kwargs): raise OSError('disk unavailable')
    monkeypatch.setattr(store,'put',fail)
    for chunk in chunks[:-1]: factory.event_artifacts.receive(chunk,channel=channel)
    with pytest.raises(OSError): factory.event_artifacts.receive(chunks[-1],channel=channel)
    with pytest.raises(ValueError,match='durably'): commit(ingress,dict(frame,events=[wire]))
    monkeypatch.setattr(store,'put',original)
    factory.event_artifacts.receive(chunks[-1],channel=channel)
    assert commit(ingress,dict(frame,events=[wire]))['sequence']==1
    with factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_artifact_settings SET quota_bytes=262144')
    _,_,more=large(ingress,300000)
    with pytest.raises(OktoNexusError,match='full'): factory.event_artifacts.receive(more[0],channel=channel)


@pytest.mark.parametrize('local_setup',['pi_rpc','claude_stream','codex_app_server'],indirect=True)
def test_embedded_large_event_reaches_terminal_history(connected_local):
    import time
    from nexus_connector_core import RuntimeEvent
    setup,binding,native=connected_local
    deps,_,client,headers,*_=setup
    opened=admit(setup,binding,'artifact-open','runtime.start',new_session=True)
    wait_receipt(setup,opened)
    session=opened['scope']['session_id']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream=dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?',(session,)).fetchone())
    content='arquivo🙂\n'*12000
    for kind,payload in [('tool_activity',{'result':content}),('turn_state',{'delivery_phase':'terminal','delivery_outcome':'success'})]:
        client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'],stream['executor_id'],session,
            stream['stream_epoch'],0,kind,'fixture',payload))
    deadline=time.monotonic()+30
    while True:
        reply=client.get(f'/v1/runtime/sessions/{session}/events',headers=headers['subject'])
        assert reply.status_code==200,reply.text
        events=reply.json()['events']
        if len(events)>=2: break
        assert time.monotonic()<deadline,reply.text
        time.sleep(.05)
    assert events[0]['payload']['result']==content
    assert events[1]['payload']['delivery_phase']=='terminal'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        saved=uow.connection.execute('SELECT payload_json FROM execution_event_ingress WHERE session_id=? AND sequence=1',(session,)).fetchone()[0]
        assert len(saved.encode())<65536 and event_reference(json.loads(saved))
    wait_receipt(setup,admit(setup,binding,'artifact-close','runtime.close',session_id=session),stages=('SUCCEEDED',))
