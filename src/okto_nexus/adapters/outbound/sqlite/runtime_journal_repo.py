"""Atomic event/result/checkpoint projection. No filesystem or native IO."""
import json


class SqliteRuntimeJournalRepo:
    def __init__(self, *, presence, sessions):
        self.presence, self.sessions = presence, sessions

    def initial_sequences(self, uow):
        return {row[0]: row[1] for row in uow.connection.execute(
            "SELECT session_id,MAX(sequence) FROM harness_events GROUP BY session_id")}

    def checkpoint(self, uow, *, store_id):
        row = uow.connection.execute("SELECT store_id,ordinal FROM runtime_journal_checkpoint WHERE singleton=1").fetchone()
        if row is None:
            return 0
        if row["store_id"] != store_id:
            raise ValueError("Journal identity does not match this database")
        return row["ordinal"]

    def project(self, uow, *, record, event, events, now):
        checkpoint = self.checkpoint(uow, store_id=record["store_id"])
        if record["ordinal"] <= checkpoint:
            return False
        if record["ordinal"] != checkpoint + 1:
            raise ValueError("Journal projector cannot skip a record")
        events.append(uow, event_id=event.event_id, event=event, created_at=now)
        if event.origin == "native" and record["connection_id"] is not None:
            session = self.sessions.get(uow, session_id=event.session_id)
            if (session and session.connection_id == record["connection_id"]
                    and session.lifecycle_state == "protocol_ready" and session.presence_session_id):
                # Preserve the observation time on delayed replay; projection
                # time does not prove that an old process is alive now.
                self.presence.heartbeat(uow, session_id=session.presence_session_id, at=event.occurred_at)
        if event.origin == "nexus" and event.native_event == "nexus/runtime_state":
            session = self.sessions.get(uow, session_id=event.session_id)
            if session is None or session.connection_id != record["connection_id"]:
                raise ValueError("Lifecycle event connection does not match its runtime")
            state = event.payload["lifecycle_state"]
            if state not in {"stop_requested", "stopped", "detached", "outcome_unknown"}:
                raise ValueError("Invalid observed lifecycle state")
            uow.connection.execute("UPDATE harness_sessions SET lifecycle_state=?,updated_at=? WHERE session_id=?",
                                   (state, now, event.session_id))
            if state != "stop_requested" and session.presence_session_id:
                self.presence.close(uow, session_id=session.presence_session_id, at=event.occurred_at)
            if state != "stop_requested":
                uow.connection.execute("UPDATE delivery_outbox SET status='OUTCOME_UNKNOWN',reason='runtime_lost',updated_at=? "
                    "WHERE runtime_session_id=? AND terminal_event_id IS NULL AND status IN ('SENDING','SENT_UNCONFIRMED','ACCEPTED')",
                    (now, event.session_id))
            if state == "stopped" and event.payload.get("stop_observed") is True:
                self.sessions.update_status(uow, session_id=event.session_id,
                    status="ERRORED" if event.payload.get("error") else "ENDED",
                    updated_at=now, ended_at=event.occurred_at)
        correlated = self._project_attempt(uow, record=record, event=event, now=now)
        if event.delivery_phase == "terminal" or (event.kind == "turn_completed" and not event.operation_id):
            uow.connection.execute("""INSERT INTO runtime_results
                (result_id,event_id,runtime_session_id,native_thread_id,native_turn_id,payload,captured_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING""", ("result_" + event.event_id, event.event_id, event.session_id,
                event.thread_id, event.turn_id, json.dumps(event.payload, ensure_ascii=False, sort_keys=True), now))
            if correlated and event.delivery_phase == "terminal":
                uow.connection.execute("UPDATE runtime_results SET operation_id=?,attempt_id=? WHERE event_id=?",
                    (event.operation_id, event.attempt_id, event.event_id))
                self._materialize_output(uow, event)
        uow.connection.execute("""INSERT INTO runtime_journal_checkpoint(singleton,store_id,ordinal,updated_at)
            VALUES(1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET ordinal=excluded.ordinal,updated_at=excluded.updated_at""",
            (record["store_id"], record["ordinal"], now))
        return True

    @staticmethod
    def _materialize_output(uow, event):
        # Bounded derived text, with all redacted source fragments still durable.
        # Iteration is bounded in memory; no filesystem/provider IO in this UoW.
        limit, used, count, truncated = 1024 * 1024, 0, 0, False
        chunks = []
        rows = uow.connection.execute("SELECT output_text,output_snapshot FROM harness_events "
            "WHERE operation_id=? AND attempt_id=? AND sequence<=? AND output_text IS NOT NULL ORDER BY sequence",
            (event.operation_id, event.attempt_id, event.sequence))
        for row in rows:
            count += 1
            if row["output_snapshot"]:
                chunks, used, truncated = [], 0, False
            raw = row["output_text"].encode("utf-8")
            available = limit - used
            if len(raw) > available:
                truncated = True
            piece = raw[:available].decode("utf-8", errors="ignore")
            chunks.append(piece)
            used += len(piece.encode("utf-8"))
        uow.connection.execute("UPDATE runtime_results SET output_text=?,output_truncated=?,output_event_count=? WHERE event_id=?",
            ("".join(chunks), int(truncated), count, event.event_id))

    def _project_attempt(self, uow, *, record, event, now):
        if event.origin != "native" or not event.operation_id or not event.attempt_id:
            return False
        session = self.sessions.get(uow, session_id=event.session_id)
        if not session or session.connection_id != record["connection_id"]:
            return False
        operation = uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?",
                                           (event.operation_id,)).fetchone()
        if (not operation or operation["runtime_session_id"] != event.session_id
                or operation["attempt_id"] != event.attempt_id
                or operation["owner_epoch"] != event.owner_epoch
                or operation["status"] not in {"SENDING", "SENT_UNCONFIRMED", "ACCEPTED"}
                or operation["terminal_event_id"] is not None):
            return False
        owner = uow.connection.execute("SELECT epoch,lease_expires_at FROM runtime_dispatcher_owner "
                                       "WHERE owner_key='dispatcher'").fetchone()
        if not owner or owner["epoch"] != event.owner_epoch or owner["lease_expires_at"] <= now:
            return False
        if event.delivery_phase == "started":
            if event.turn_id and uow.connection.execute(
                    "SELECT 1 FROM delivery_outbox WHERE runtime_session_id=? AND native_turn_id=? AND operation_id<>?",
                    (event.session_id, event.turn_id, event.operation_id)).fetchone():
                return False
            uow.connection.execute("UPDATE delivery_outbox SET status='ACCEPTED',ack_level='HARNESS_ACCEPTED',"
                "native_thread_id=?,native_turn_id=?,updated_at=? WHERE operation_id=? AND status IN ('SENDING','SENT_UNCONFIRMED')",
                (event.thread_id, event.turn_id, now, event.operation_id))
            return True
        if (operation["status"] != "ACCEPTED" or operation["native_thread_id"] != event.thread_id
                or operation["native_turn_id"] != event.turn_id):
            return False
        if event.delivery_phase == "terminal":
            uow.connection.execute("UPDATE delivery_outbox SET terminal_event_id=?,reason='result_durable',updated_at=? "
                                   "WHERE operation_id=?", (event.event_id, now, event.operation_id))
        return True
