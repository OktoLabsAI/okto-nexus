"""Disposable production HTTP owner for crash tests; never launches a model."""
import itertools
import json
import os
from pathlib import Path
import socket
import sys
import threading

import uvicorn

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from okto_nexus.adapters.outbound.sqlite.runtime_journal_repo import SqliteRuntimeJournalRepo
from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.base import iso_plus, utc_now_iso
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def main():
    home, root, ready_path = map(Path, sys.argv[1:4])
    cut, offset = sys.argv[4], int(sys.argv[5])
    deps = bootstrap({}, ["--home", str(home)])
    deps.config.feature_harness_integrations = True
    deps.config.max_relay_depth = 4
    # Advance only the test application's clock to exercise lease/deadline
    # boundaries without waiting real minutes or modifying persisted leases.
    deps.clock.now_iso = lambda: iso_plus(utc_now_iso(), offset)
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    operator_file = home / "fixture-operator.json"
    if issued:
        operator_file.write_text(json.dumps(issued[1]), encoding="utf-8")
    operator = json.loads(operator_file.read_text(encoding="utf-8"))
    caller_file = home / "fixture-caller.json"
    if not caller_file.exists():
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.agents.upsert(uow, agent_id="worker")
            deps.repos.agents.upsert(uow, agent_id="caller")
            caller = auth.issue_key(uow, agent_id="caller")
        caller_file.write_text(json.dumps(caller), encoding="utf-8")
    caller = json.loads(caller_file.read_text(encoding="utf-8"))
    source = _FAKE_SERVER_SOURCE.replace("def next_thread_id():", "log({'fixture_pid': os.getpid()})\n\ndef next_thread_id():")
    insertion = '''def handle_turn(thread_id, turn_id, text, req_id):
    envelope = json.loads(text.split("\\n", 1)[1])
    log({"fixture_operation": envelope["operation_id"], "recipient": envelope["recipient_agent_id"]})
'''
    if cut == "accepted_child":
        insertion += '    if envelope["recipient_agent_id"] == "caller": text += " TRIGGER_HOLD"\n'
    source = source.replace("def handle_turn(thread_id, turn_id, text, req_id):\n", insertion)
    peer_script = home / f"peer-{os.getpid()}.py"
    peer_script.write_text(source, encoding="utf-8")
    counter = itertools.count()
    deps.harness_connector_factories = {"codex": lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", str(peer_script), str(home / f"native-{os.getpid()}-{next(counter)}.jsonl")],
        cwd=str(root), env=kwargs["backend"]["env"])}

    if cut in {"before_output_capture", "before_terminal_capture"}:
        from okto_nexus.adapters.outbound.harness.event_journal import FileRuntimeEventJournal

        append = FileRuntimeEventJournal.append

        def exit_before_capture(self, event, **kwargs):
            targeted = (event.kind == "output_delta" if cut == "before_output_capture"
                else event.delivery_phase == "terminal")
            if targeted and event.operation_id:
                # Observe the actual native event but kill the owner before the
                # journal append/fsync. This marker is test evidence, not replay.
                (home / "uncaptured-event.json").write_text(json.dumps({
                    "operation_id": event.operation_id, "attempt_id": event.attempt_id,
                    "kind": event.kind, "phase": event.delivery_phase,
                    "watermark": self.watermark}), encoding="utf-8")
                os._exit(78)
            return append(self, event, **kwargs)

        FileRuntimeEventJournal.append = exit_before_capture

    project = SqliteRuntimeJournalRepo.project
    def project_at_cut(self, uow, **kwargs):
        event = kwargs["event"]
        if cut == "journal_terminal" and event.delivery_phase == "terminal":
            os._exit(73)  # append/fsync returned, projection has not committed.
        if cut == "accepted_child" and event.delivery_phase == "started":
            operation = uow.connection.execute("SELECT source_result_id FROM delivery_outbox WHERE operation_id=?",
                (event.operation_id,)).fetchone()
            if operation and operation[0]:
                os._exit(75)  # Peer emitted acceptance; no terminal is available.
        return project(self, uow, **kwargs)
    SqliteRuntimeJournalRepo.project = project_at_cut
    if cut == "projection_commit":
        from okto_nexus.application.runtime_event_ingress import RuntimeEventIngress
        from okto_nexus.application.runtime_results import RuntimeResultService

        # Keep result publication pending until the owner has been killed.
        # Projection, canonical consumption and its receipt remain unmodified.
        RuntimeResultService.scan_once = lambda *args, **kwargs: 0
        recover = RuntimeEventIngress.recover

        def exit_after_projection_commit(self):
            count = recover(self)
            with self.cf.unit_of_work(write=False) as uow:
                result = uow.connection.execute("SELECT r.event_id,r.operation_id,o.delivery_id "
                    "FROM runtime_results r JOIN delivery_outbox o USING(operation_id) "
                    "WHERE o.terminal_event_id=r.event_id").fetchone()
                if result is None:
                    return count
                marker = dict(result)
                marker["checkpoint"] = self.repo.checkpoint(uow, store_id=self.journal.store_id)
                marker["receipt_count"] = uow.connection.execute("SELECT count(*) FROM messages "
                    "WHERE subject LIKE 'runtime processing receipt:%'").fetchone()[0]
                marker["delivery_status"] = uow.connection.execute("SELECT status FROM message_deliveries "
                    "WHERE delivery_id=?", (result["delivery_id"],)).fetchone()[0]
            # This independent read transaction observes the already committed
            # event/result/consumption/checkpoint. File I/O is outside its UoW.
            (home / "projection-committed.json").write_text(json.dumps(marker), encoding="utf-8")
            os._exit(77)

        RuntimeEventIngress.recover = exit_after_projection_commit
    pending = SqliteRuntimeOutboxRepo.pending
    def pending_at_cut(self, uow, **kwargs):
        if cut == "message_commit":
            return []  # Hold dispatch until the post-commit cut, without changing admission.
        rows = pending(self, uow, **kwargs)
        if cut == "committed_child" and any(row["source_result_id"] for row in rows):
            os._exit(74)  # Another transaction can see the committed child.
        return rows
    SqliteRuntimeOutboxRepo.pending = pending_at_cut
    if cut == "message_commit":
        from okto_nexus.adapters.inbound.mcp.tools import messages

        def exit_before_wake(current_deps):
            # A new transaction must observe all committed canonical rows before
            # killing the entire owner. The actual wake implementation never runs.
            with current_deps.connection_factory.unit_of_work(write=False) as uow:
                committed = {table: uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    for table in ("messages", "message_deliveries", "delivery_outbox")}
            assert committed == {"messages": 1, "message_deliveries": 1, "delivery_outbox": 1}, committed
            (home / "commit-before-wake.json").write_text(json.dumps(committed), encoding="utf-8")
            os._exit(76)

        messages.wake_runtime = exit_before_wake


    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            temporary = ready_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"url": url, "operator": operator, "caller": caller,
                "owner_pid": os.getpid()}), encoding="utf-8")
            temporary.replace(ready_path)
    server = Server(uvicorn.Config(build_app(deps, runtime_owner_api_url=url), log_level="error"))
    def control():
        for line in sys.stdin:
            if line.strip() == "stop":
                server.should_exit = True
                return
            if line.strip() == "wake":
                deps.runtime_dispatcher.wake()
    threading.Thread(target=control, daemon=True).start()
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
