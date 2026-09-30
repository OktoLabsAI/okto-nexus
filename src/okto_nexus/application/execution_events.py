"""Transactional R4 event ingress; acknowledge only committed contiguous facts."""
import hashlib
from datetime import datetime, timezone

from nexus_connector_core import (
    R4EventCommitProjection, decode_r4_frame, encode_r4_frame,
    reduce_r4_durable_event_batch, r4_event_ack_frame,
)
from nexus_connector_core.protocol import canonical_json
from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from .execution_leases import require_execution_lane


def commit_execution_events(factory, *, channel, frame, embedded_owner=None):
    frame = decode_r4_frame(encode_r4_frame(frame))
    if frame["type"] != "event.batch" or any(frame[k] != getattr(channel,k) for k in (
            "server_id","executor_id","connection_id","connection_generation")):
        raise ValueError("The event channel does not match its authenticated owner.")
    _, revisions, _ = current_agent_revisions(factory, agent_id=frame["agent_id"])
    scope = {**frame, "credential_epoch":revisions.credential_epoch,
             "authorization_revision":revisions.authorization, "configuration_revision":revisions.configuration}
    key = tuple(frame[k] for k in ("server_id","executor_id","session_id","stream_epoch"))
    prepared = []
    for event in frame["events"]:
        raw = canonical_json(event)
        if len(raw) > 64 * 1024 or event["sequence"] > 9007199254740991:
            raise ValueError("The event exceeds its storage limit.")
        if any(event[k] != frame[k] for k in ("server_id","executor_id","session_id","stream_epoch")):
            raise ValueError("The event stream does not match its envelope.")
        prepared.append((event,raw.decode(),"sha256:"+hashlib.sha256(raw).hexdigest()))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        if not SqliteExecutionLeaseRepository().current_channel(uow,channel):
            raise ValueError("The event owner is no longer current.")
        current = conn.execute("SELECT credential_epoch,authorization_revision,configuration_revision "
            "FROM execution_agent_revisions WHERE server_id=? AND agent_id=?",
            (frame["server_id"],frame["agent_id"])).fetchone()
        if current is None or tuple(current) != (scope["credential_epoch"],scope["authorization_revision"],scope["configuration_revision"]):
            raise ValueError("The event authority changed.")
        if embedded_owner is None:
            require_execution_lane(uow,scope=scope,channel=channel,now=datetime.now(timezone.utc))
        else:
            embedded_owner.verify(uow=uow)
            if embedded_owner.channel != channel or conn.execute(
                    "SELECT 1 FROM execution_local_streams l JOIN execution_local_publications p "
                    "ON p.server_id=l.server_id AND p.executor_id=l.executor_id AND p.operation_id=l.opening_operation_id "
                    "WHERE l.server_id=? AND l.executor_id=? AND l.session_id=? AND l.stream_epoch=? "
                    "AND l.binding_id=? AND l.agent_id=?",
                    (*key,frame["binding_id"],frame["agent_id"])).fetchone() is None:
                raise ValueError("The event has no approved embedded stream.")
        session = conn.execute("SELECT s.stream_epoch,ep.agent_id,a.is_active FROM execution_sessions s "
            "JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id "
            "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id JOIN agents a ON a.agent_id=ep.agent_id "
            "WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.binding_id=?",
            (*key[:3],frame["binding_id"])).fetchone()
        if session is None or session["agent_id"] != frame["agent_id"] or not session["is_active"] or session["stream_epoch"] not in (None,key[3]):
            raise ValueError("The event has no matching authorized session.")
        row = conn.execute("SELECT committed_contiguous FROM execution_event_watermarks WHERE "
                           "server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",key).fetchone()
        watermark = row[0] if row else 0
        known = {}
        rows = conn.execute("SELECT sequence,event_hash,payload_json FROM execution_event_ingress WHERE "
            "server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence>? ORDER BY sequence LIMIT 512",
            (*key,max(0,watermark-256))).fetchall()
        for saved in rows:
            if "sha256:"+hashlib.sha256(saved["payload_json"].encode()).hexdigest() != saved["event_hash"]:
                raise ValueError("Stored event integrity validation failed.")
            known[saved["sequence"]] = saved["event_hash"][7:]
        for event,raw,digest in prepared:
            sequence = event["sequence"]
            prior = conn.execute("SELECT event_hash,payload_json FROM execution_event_ingress WHERE "
                "server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence=?",(*key,sequence)).fetchone()
            if prior is not None:
                if prior["event_hash"] != digest or prior["payload_json"] != raw:
                    raise ValueError("The event sequence has conflicting content.")
                known[sequence] = digest[7:]
            elif sequence <= watermark:
                raise ValueError("The acknowledged event is missing from durable storage.")
            operation_id = event.get("operation_id")
            if operation_id is not None and conn.execute("SELECT 1 FROM execution_operations WHERE "
                    "server_id=? AND executor_id=? AND session_id=? AND binding_id=? AND subject_agent_id=? AND operation_id=?",
                    (*key[:3],frame["binding_id"],frame["agent_id"],operation_id)).fetchone() is None:
                raise ValueError("The event operation is outside its session.")
        previous = R4EventCommitProjection(*(frame[k] for k in (
            "server_id","executor_id","binding_id","agent_id","session_id","stream_epoch")),
            channel.connection_id,channel.connection_generation,watermark,
            tuple((s,h) for s,h in known.items() if s<=watermark),
            tuple((s,h) for s,h in known.items() if s>watermark))
        projection = reduce_r4_durable_event_batch(previous,frame,
            connection_id=channel.connection_id,connection_generation=channel.connection_generation)
        for event,raw,digest in prepared:
            conn.execute("INSERT OR IGNORE INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,"
                "sequence,event_hash,event_type,payload_json,received_at) VALUES (?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                (*key,event["sequence"],digest,event["category"],raw))
        conn.execute("UPDATE execution_sessions SET stream_epoch=? WHERE server_id=? AND executor_id=? AND session_id=?",
                     (key[3],*key[:3]))
        conn.execute("INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,"
            "committed_contiguous,gap_state) VALUES (?,?,?,?,?,?) ON CONFLICT(server_id,executor_id,session_id,stream_epoch) "
            "DO UPDATE SET committed_contiguous=excluded.committed_contiguous,gap_state=excluded.gap_state",
            (*key,projection.watermark,"pending" if projection.pending else "none"))
    # The transaction context has committed before an ACK can reach a socket.
    return r4_event_ack_frame(projection) if projection.watermark else None
