"""Reconciliation readiness requires durable, current, complete evidence."""
import json
import hashlib
import pytest
from nexus_connector_core import encode_r4_frame
from okto_nexus.application.execution_leases import ExecutionChannel
from okto_nexus.application.execution_reconciliation import ExecutionReconciliation
from okto_nexus.adapters.outbound.sqlite.execution_tickets import VerifiedExecutionTicket
from test_binding_operator import onboarding, prepare_operator
from test_ns02_receipts import _receipt


def seed_receipt(factory, frame):
    # Durable precondition only. Real authenticated ingress is exercised in
    # test_remote_connection, including receipt publication after lost ACK.
    raw = encode_r4_frame(frame).decode("utf-8")
    row = {k:frame[k] for k in ("server_id","executor_id","operation_id","receipt_revision",
                               "intent_hash","stage","possible_effect","retry_safe")}
    row.update(received_at="2026-09-30T00:00:00Z",canonical_frame=raw,
               frame_digest="sha256:"+hashlib.sha256(raw.encode()).hexdigest(),
               source_connection_id=frame["connection_id"],
               source_connection_generation=frame["connection_generation"])
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO execution_receipts (" + ",".join(row) + ") VALUES (" +
                               ",".join("?" for _ in row) + ")",tuple(row.values()))


@pytest.fixture
def recovery(onboarding):
    deps, client, headers, prepare = onboarding
    _, apply = prepare_operator(client, headers, prepare)
    response = client.post("/v1/connections/bindings:apply", json=apply, headers=headers["operator"])
    assert response.status_code == 200, response.text
    factory = deps.connection_factory
    with factory.unit_of_work() as uow:
        conn = uow.connection
        binding = conn.execute("SELECT * FROM execution_bindings").fetchone()
        server, executor = binding["server_id"], binding["executor_id"]
        conn.execute("UPDATE execution_executors SET control_state='RECOVERING', "
                     "owner_instance_id='connection',generation=2 WHERE server_id=? AND executor_id=?",
                     (server, executor))
        values = dict(server_id=server, executor_id=executor, operation_id="close",
            subject_agent_id="subject", actor_agent_id="subject", binding_id=binding["binding_id"],
            workspace_id=prepare["workspace_id"], workspace_binding_id=binding["workspace_binding_id"],
            session_id="session", action="runtime.close", intent_hash="sha256:" + "a"*64,
            semantic_payload="{}", expected_revisions_json=json.dumps({"session_owner_generation":1}),
            admission_state="ACCEPTED", created_at=deps.clock.now_iso())
        conn.execute("INSERT INTO execution_operations (" + ",".join(values) + ") VALUES (" +
                     ",".join("?" for _ in values) + ")", tuple(values.values()))
        conn.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,"
            "workspace_id,workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,lease_state)"
            " VALUES (?,?,?,?,?,?,'open',1,'READY','SUPERSEDED')",
            (server,executor,"session",binding["binding_id"],prepare["workspace_id"],binding["workspace_binding_id"]))
    frame = _receipt(server,executor,operation_id="close",binding_id=binding["binding_id"],
                     agent_id="subject",stage="SUCCEEDED",possible_effect=True,retry_safe=False)
    principal = VerifiedExecutionTicket("ticket",server,executor,binding["binding_id"],"subject",
                                        frozenset({"receipt:publish"}),1,1)
    seed_receipt(factory, frame)
    # Simulate a session row whose close receipt committed before ownership reconciliation.
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY',lease_state='SUPERSEDED'")
        uow.connection.execute("UPDATE execution_operations SET admission_state='DISPATCHED'")
    service = ExecutionReconciliation(factory, ExecutionChannel(server,executor,"connection",2))
    request = service.request()
    report = {k:v for k,v in request.items() if k not in ("operation_ids","session_ids","stream_watermarks")}
    report.update(type="reconcile.report",complete=True,next_cursor=None,
        receipts=[{k:frame[k] for k in ("operation_id","intent_hash","receipt_revision","stage")}],
        claims=[dict(session_id="session",owner_generation=1,state="RELEASED")],
        ownership_facts=[dict(session_id="session",owner_generation=1,process_state="EXITED",
                              proof_digest="sha256:"+"b"*64)],
        stream_watermarks=[dict(session_id="session",stream_epoch="epoch",sequence=0)])
    return factory,service,report,principal,frame


def state(factory):
    with factory.unit_of_work(write=False) as uow:
        return uow.connection.execute("SELECT control_state FROM execution_executors "
                                      "WHERE owner_instance_id='connection'").fetchone()[0]


def test_confirmed_close_makes_current_owner_ready(recovery):
    factory,service,report,_,_ = recovery
    assert service.accept(report)["recovery_remaining"] is False
    assert state(factory) == "CONTROL_READY"


@pytest.mark.parametrize("fault", [
    "hash", "revision", "stage", "missing_receipt", "corrupt_frame", "corrupt_digest",
    "unknown_claim", "unknown_process", "wrong_owner", "missing_proof", "missing_watermark",
    "nonzero_watermark", "missing_close", "receipt_after_snapshot",
])
def test_incomplete_or_invalid_evidence_never_makes_owner_ready(recovery, fault):
    factory,service,report,principal,frame = recovery
    if fault in ("hash","revision","stage"):
        field,value = {"hash":("intent_hash","sha256:"+"f"*64),
                       "revision":("receipt_revision",2),"stage":("stage","RUNNING")}[fault]
        report["receipts"][0][field] = value
    elif fault == "missing_receipt":
        report["receipts"] = []
    elif fault in ("corrupt_frame","corrupt_digest","missing_close"):
        sql = {"corrupt_frame":"UPDATE execution_receipts SET canonical_frame='{}'",
               "corrupt_digest":"UPDATE execution_receipts SET frame_digest='sha256:corrupt'",
               "missing_close":"UPDATE execution_operations SET action='turn.submit'"}[fault]
        with factory.unit_of_work() as uow:
            uow.connection.execute(sql)
    elif fault == "unknown_claim":
        report["claims"][0]["state"] = "UNKNOWN"
    elif fault == "unknown_process":
        report["ownership_facts"][0]["process_state"] = "UNKNOWN"
    elif fault == "wrong_owner":
        report["claims"][0]["owner_generation"] = 2
        report["ownership_facts"][0]["owner_generation"] = 2
    elif fault == "missing_proof":
        report["ownership_facts"][0].pop("proof_digest")
    elif fault == "missing_watermark":
        report["stream_watermarks"] = []
    elif fault == "nonzero_watermark":
        report["stream_watermarks"][0]["sequence"] = 1
    elif fault == "receipt_after_snapshot":
        seed_receipt(factory, {**frame,"receipt_revision":2})
    assert service.accept(report)["recovery_remaining"] is True
    assert state(factory) == "RECOVERING"


@pytest.mark.parametrize("fault", [
    "connection_generation", "connection_id", "server_id", "executor_id", "reconcile_id",
    "cursor", "owner_changed", "duplicate_receipt", "duplicate_claim", "duplicate_stream",
    "unmatched_fact", "nonadvancing_cursor",
])
def test_stale_or_malformed_report_is_rejected(recovery, fault):
    factory,service,report,_,_ = recovery
    if fault in ("connection_generation","connection_id","server_id","executor_id","reconcile_id","cursor"):
        report[fault] = 999 if fault == "connection_generation" else "stale"
    elif fault == "owner_changed":
        with factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_executors SET generation=3")
    elif fault.startswith("duplicate_"):
        field = {"duplicate_receipt":"receipts","duplicate_claim":"claims","duplicate_stream":"stream_watermarks"}[fault]
        report[field].append(dict(report[field][0]))
    elif fault == "unmatched_fact":
        report["ownership_facts"][0]["session_id"] = "foreign"
    elif fault == "nonadvancing_cursor":
        report.update(complete=False,next_cursor=None)
    with pytest.raises(ValueError):
        service.accept(report)
    assert state(factory) == "RECOVERING"


@pytest.mark.parametrize("reported,epoch,gap,ready",[(1,"epoch","none",True),(0,"epoch","none",False),
    (2,"epoch","none",False),(1,"other","none",False),(1,"epoch","pending",False)])
def test_stream_readiness_requires_matching_durable_contiguous_prefix(recovery,reported,epoch,gap,ready):
    factory,service,report,_,_=recovery
    c=service.channel
    with factory.unit_of_work() as uow:
        conn=uow.connection
        conn.execute("UPDATE execution_sessions SET stream_epoch=?",(epoch,))
        conn.execute("INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,"
                     "committed_contiguous,gap_state) VALUES (?,?,'session','epoch',1,?)",(c.server_id,c.executor_id,gap))
    report["stream_watermarks"][0]["sequence"]=reported
    assert service.accept(report)["recovery_remaining"] is not ready
