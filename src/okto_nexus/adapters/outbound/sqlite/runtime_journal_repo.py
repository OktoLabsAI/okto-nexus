"""Atomic event/result/checkpoint projection. No filesystem or native IO."""
import json


class SqliteRuntimeJournalRepo:
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
        if event.kind == "turn_completed":
            uow.connection.execute("""INSERT INTO runtime_results
                (result_id,event_id,runtime_session_id,native_thread_id,native_turn_id,payload,captured_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING""", ("result_" + event.event_id, event.event_id, event.session_id,
                event.thread_id, event.turn_id, json.dumps(event.payload, ensure_ascii=False, sort_keys=True), now))
        uow.connection.execute("""INSERT INTO runtime_journal_checkpoint(singleton,store_id,ordinal,updated_at)
            VALUES(1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET ordinal=excluded.ordinal,updated_at=excluded.updated_at""",
            (record["store_id"], record["ordinal"], now))
        return True
