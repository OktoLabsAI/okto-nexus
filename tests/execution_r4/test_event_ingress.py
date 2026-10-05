"""Event ingestion persists gaps and authenticates the current binding lane."""
import pytest
from nexus_connector_core import CoreError, R4_PREVIEW_REVISION
from okto_nexus.application.execution_events import commit_execution_events
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
from okto_nexus.errors import OktoNexusError
from test_reconciliation import recovery
from test_binding_operator import onboarding


@pytest.fixture
def ingress(recovery):
    factory,service,_,_,receipt = recovery
    c = service.channel
    _,revisions,_ = current_agent_revisions(factory,agent_id="subject")
    issued = issue_execution_ticket(factory,server_id=c.server_id,executor_id=c.executor_id,
        agent_id="subject",binding_id=receipt["binding_id"],scopes=frozenset({"lane:attach","lease:request"}))
    # Focused service precondition; public lane attachment is covered in the
    # public_open_bootstrap HTTP/WSS integration.
    with factory.unit_of_work() as uow:
        conn=uow.connection
        ticket=conn.execute("SELECT * FROM execution_link_tickets WHERE binding_id=? ORDER BY rowid DESC LIMIT 1",
                           (receipt["binding_id"],)).fetchone()
        conn.execute("UPDATE execution_link_tickets SET bound_connection_id=? WHERE ticket_id=?",
                     (c.connection_id,ticket["ticket_id"]))
        conn.execute("INSERT INTO execution_control_lanes(server_id,executor_id,binding_id,agent_id,ticket_id,"
            "attach_request_id,connection_id,connection_generation,credential_epoch,authorization_revision,"
            "configuration_revision,expires_at,state) VALUES (?,?,?,'subject',?,'attach',?,?,?,?,?,?,'ADMITTED')",
            (c.server_id,c.executor_id,receipt["binding_id"],ticket["ticket_id"],c.connection_id,c.connection_generation,
             revisions.credential_epoch,revisions.authorization,revisions.configuration,ticket["expires_at"]))
    event=dict(server_id=c.server_id,executor_id=c.executor_id,session_id="session",stream_epoch="epoch",
               sequence=1,category="text_delta",payload={"text":"Hello"},operation_id="close")
    frame=dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type="event.batch",
        server_id=c.server_id,executor_id=c.executor_id,binding_id=receipt["binding_id"],agent_id="subject",
        session_id="session",stream_epoch="epoch",connection_id=c.connection_id,
        connection_generation=c.connection_generation,events=[event])
    return factory,c,frame


def commit(ingress, frame=None):
    factory,channel,batch=ingress
    return commit_execution_events(factory,channel=channel,frame=frame or batch)


def snapshot(factory):
    with factory.unit_of_work(write=False) as uow:
        return ([tuple(r) for r in uow.connection.execute("SELECT * FROM execution_event_ingress ORDER BY sequence")],
                [tuple(r) for r in uow.connection.execute("SELECT * FROM execution_event_watermarks")])


def test_gap_replay_and_conflict(ingress):
    factory,channel,frame=ingress
    third={**frame,"events":[{**frame["events"][0],"sequence":3}]}
    assert commit(ingress,third) is None
    assert commit(ingress)["sequence"] == 1
    assert commit(ingress,{**frame,"events":[{**frame["events"][0],"sequence":2}]})["sequence"] == 3
    saved=snapshot(factory)
    assert commit(ingress)["sequence"] == 3
    assert snapshot(factory)==saved
    with pytest.raises(ValueError,match="conflicting"):
        commit(ingress,{**frame,"events":[{**frame["events"][0],"payload":{"text":"Changed"}}]})
    assert snapshot(factory)==saved


@pytest.mark.parametrize("fault", [
    "wrong_channel","wrong_event_scope","wrong_session","wrong_binding","wrong_agent","unknown_operation",
    "epoch_changed","expired_lane","revoked_ticket","old_generation","changed_revision","oversized","far_gap",
])
def test_invalid_events_leave_storage_unchanged(ingress,fault):
    factory,channel,frame=ingress
    assert commit(ingress)["sequence"] == 1
    saved=snapshot(factory)
    frame={**frame,"events":[{**frame["events"][0],"sequence":2}]}
    if fault=="wrong_channel": frame["connection_id"]="other"
    elif fault=="wrong_event_scope": frame["events"][0]["executor_id"]="other"
    elif fault=="wrong_session":
        frame["session_id"]=frame["events"][0]["session_id"]="other"
    elif fault=="wrong_binding": frame["binding_id"]="other"
    elif fault=="wrong_agent": frame["agent_id"]="other"
    elif fault=="unknown_operation": frame["events"][0]["operation_id"]="absent"
    elif fault=="epoch_changed":
        frame["stream_epoch"]=frame["events"][0]["stream_epoch"]="other"
    elif fault=="oversized": frame["events"][0]["payload"]={"text":"x"*65536}
    elif fault=="far_gap": frame["events"][0]["sequence"]=258
    else:
        sql={"expired_lane":"UPDATE execution_control_lanes SET expires_at='2000-01-01T00:00:00Z'",
             "revoked_ticket":"UPDATE execution_link_tickets SET revoked_at='now'",
             "old_generation":"UPDATE execution_executors SET generation=3",
             "changed_revision":"UPDATE agents SET is_active=0 WHERE agent_id='subject'"}[fault]
        with factory.unit_of_work() as uow: uow.connection.execute(sql)
    with pytest.raises((ValueError,CoreError,OktoNexusError)):
        commit(ingress,frame)
    assert snapshot(factory)==saved


def test_storage_failure_never_returns_ack(ingress):
    factory,_,_=ingress
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_watermark BEFORE INSERT ON execution_event_watermarks "
                               "BEGIN SELECT RAISE(ABORT,'Injected watermark failure'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        commit(ingress)
    assert snapshot(factory)==([],[])


def test_old_duplicate_survives_reopening_beyond_reducer_window(ingress):
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    factory,channel,frame=ingress
    for start in (1,101,201):
        batch={**frame,"events":[{**frame["events"][0],"sequence":n} for n in range(start,start+100)]}
        assert commit(ingress,batch)["sequence"]==start+99
    reopened=ConnectionFactory(factory.config)
    assert commit_execution_events(reopened,channel=channel,frame=frame)["sequence"]==300
    assert len(snapshot(reopened)[0])==300
    with reopened.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_event_ingress SET payload_json='{}' WHERE sequence=300")
    with pytest.raises(ValueError,match="integrity"):
        commit_execution_events(reopened,channel=channel,frame=frame)
