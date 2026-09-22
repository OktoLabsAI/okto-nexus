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
            if state == "stopped" and event.payload.get("stop_observed") is True:
                self.sessions.update_status(uow, session_id=event.session_id,
                    status="ERRORED" if event.payload.get("error") else "ENDED",
                    updated_at=now, ended_at=event.occurred_at)
        if event.kind == "turn_completed":
            uow.connection.execute("""INSERT INTO runtime_results
                (result_id,event_id,runtime_session_id,native_thread_id,native_turn_id,payload,captured_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING""", ("result_" + event.event_id, event.event_id, event.session_id,
                event.thread_id, event.turn_id, json.dumps(event.payload, ensure_ascii=False, sort_keys=True), now))
        uow.connection.execute("""INSERT INTO runtime_journal_checkpoint(singleton,store_id,ordinal,updated_at)
            VALUES(1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET ordinal=excluded.ordinal,updated_at=excluded.updated_at""",
            (record["store_id"], record["ordinal"], now))
        return True
