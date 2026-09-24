"""Bounded, in-process instrumentation for the isolated operational campaign.

Not a production exporter. Never write logs, query databases or inspect processes
from a write-transaction hook. Only the explicit outside-transaction snapshot
reads aggregate state. Identifiers remain private correlation keys in memory.
"""
from collections import Counter
import os
from pathlib import Path
import threading
import time


class OperationalProbe:
    def __init__(self, limit=256):
        self.limit = limit
        self.rows = {}
        self.lock = threading.RLock()
        self.restorations = []
        self.overflow = False
        self.snapshots = []
        self.duplicate_http_requests = 0
        self.shutdown_ms = None

    def mark(self, operation, **values):
        if not operation:
            return
        with self.lock:
            if operation not in self.rows and len(self.rows) >= self.limit:
                self.overflow = True
                return
            row = self.rows.setdefault(operation, {})
            for key, value in values.items():
                row.setdefault(key, value)

    def patch(self, owner, name, wrap):
        original = getattr(owner, name)
        setattr(owner, name, wrap(original))
        self.restorations.append((owner, name, original))

    def install(self):
        from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
        from okto_nexus.adapters.outbound.sqlite.runtime_commands_repo import SqliteRuntimeCommandRepo
        from okto_nexus.adapters.outbound.sqlite.runtime_journal_repo import SqliteRuntimeJournalRepo
        from okto_nexus.adapters.outbound.harness.event_journal import FileRuntimeEventJournal
        from okto_nexus.application.runtime_control import RuntimeControlService

        def enqueue(original):
            def measured(repo, uow, **kwargs):
                result = original(repo, uow, **kwargs)
                uow._metric_probe_enqueues = [*getattr(uow, "_metric_probe_enqueues", []), result["operation_id"]]
                return result
            return measured

        def project(original):
            def measured(repo, uow, **kwargs):
                result = original(repo, uow, **kwargs)
                event = kwargs["event"]
                if result and event.operation_id and event.delivery_phase == "terminal":
                    uow._metric_probe_terminals = [*getattr(uow, "_metric_probe_terminals", []), event.operation_id]
                return result
            return measured

        def commit(original):
            def measured(uow):
                start = time.perf_counter_ns()
                result = original(uow)
                end = time.perf_counter_ns()
                for operation in getattr(uow, "_metric_probe_enqueues", []):
                    self.mark(operation, commit_begin=start, commit_end=end)
                for operation in getattr(uow, "_metric_probe_terminals", []):
                    self.mark(operation, projected=end)
                return result
            return measured

        def execute(original):
            def measured(service, command):
                self.mark(command["operation_id"], dispatch=time.perf_counter_ns())
                with self.lock:
                    row = self.rows.get(command["operation_id"])
                    if row is not None:
                        row["dispatch_calls"] = row.get("dispatch_calls", 0) + 1
                return original(service, command)
            return measured

        def append(original):
            def measured(journal, event, **kwargs):
                start = time.perf_counter_ns()
                if event.origin == "native" and event.operation_id:
                    self.mark(event.operation_id, first_event=start)
                    if event.delivery_phase == "started":
                        self.mark(event.operation_id, accepted=start)
                    elif event.delivery_phase == "terminal":
                        self.mark(event.operation_id, terminal=start)
                result = original(journal, event, **kwargs)
                if event.origin == "native" and event.delivery_phase == "terminal":
                    self.mark(event.operation_id, durable=time.perf_counter_ns())
                return result
            return measured

        self.patch(SqliteRuntimeCommandRepo, "enqueue", enqueue)
        self.patch(SqliteRuntimeJournalRepo, "project", project)
        self.patch(SqliteUnitOfWork, "commit", commit)
        self.patch(RuntimeControlService, "execute", execute)
        self.patch(FileRuntimeEventJournal, "append", append)

    def restore(self):
        for owner, name, original in reversed(self.restorations):
            setattr(owner, name, original)
        self.restorations.clear()

    def snapshot(self, deps, peers, label):
        # These observations are deliberately outside all writer hooks/UoWs.
        if os.name == "nt":
            import psutil
            process = psutil.Process()
            resources = {"rss_bytes": process.memory_info().rss, "threads": process.num_threads(),
                         "handles": process.num_handles(), "source": "psutil-current-process"}
        else:
            status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
            resources = {"rss_bytes": int(status["VmRSS"].split()[0]) * 1024,
                         "threads": int(status["Threads"]), "fds": len(list(Path("/proc/self/fd").iterdir())),
                         "source": "linux-proc-self"}
        with deps.connection_factory.unit_of_work(write=False) as uow:
            db = uow.connection
            states = {table: dict(db.execute(f"SELECT status,count(*) FROM {table} GROUP BY status").fetchall())
                      for table in ("delivery_outbox", "runtime_commands")}
            lanes = [r[0] for r in db.execute("SELECT count(*) FROM ("
                "SELECT endpoint_id AS lane FROM runtime_commands WHERE reconciliation_id IS NULL AND status IN "
                "('PENDING','CLAIMED','SENDING') UNION ALL SELECT COALESCE(json_extract(next_binding,'$.endpoint_id'),endpoint_id) "
                "FROM delivery_outbox WHERE reconciliation_id IS NULL AND status IN ('PENDING','RETRY_WAIT','CLAIMED','SENDING')) GROUP BY lane")]
            checkpoint = db.execute("SELECT COALESCE(max(ordinal),0) FROM runtime_journal_checkpoint").fetchone()[0]
            denials = db.execute("SELECT count(*) FROM runtime_access_audit WHERE decision='deny'").fetchone()[0]
            retries = db.execute("SELECT count(*) FROM runtime_delivery_attempt_events WHERE state='RETRY_WAIT'").fetchone()[0]
            budgets = dict(zip(("roots", "generated_messages", "admitted_executions"), db.execute(
                "SELECT count(*),COALESCE(sum(generated_messages),0),COALESCE(sum(admitted_executions),0) FROM runtime_causal_roots").fetchone()))
            uncorrelated = db.execute("SELECT count(*) FROM harness_events WHERE origin='native' AND operation_id IS NULL").fetchone()[0]
        journal = deps.harness_supervisor.event_ingress.journal.diagnostics()
        self.snapshots.append({"phase": label, "states": states, "queued_or_dispatching_lanes": len(lanes),
            "maximum_queued_or_dispatching_per_lane": max(lanes, default=0), "journal_bytes": journal["retained_bytes"],
            "journal_watermark": journal["watermark"], "projected_watermark": checkpoint,
            "journal_lag_records": journal["watermark"] - checkpoint, "runtime_authorization_denials": denials,
            "safe_retry_observations": retries, "budgets": budgets, "uncorrelated_native_events": uncorrelated,
            "live_bindings": len(deps.harness_supervisor.list_live()),
            "owned_native_processes_alive": sum(p._transport._proc.poll() is None for p in peers),
            "owner_resources": resources})

    def report(self):
        samples = []
        missing = Counter()
        required = {"commit_begin", "commit_end", "dispatch", "first_event", "accepted", "terminal", "durable", "projected", "request_start", "admitted"}
        with self.lock:
            for row in self.rows.values():
                if "request_start" not in row:
                    continue  # Administrative close has no measured prompt.
                absent = required - row.keys()
                if absent:
                    missing.update(absent)
                    continue
                samples.append({
                    "dispatch_calls": row["dispatch_calls"],
                    "admission_ms": (row["admitted"] - row["request_start"]) / 1e6,
                    "commit_to_dispatch_ms_bounds": [max(0, row["dispatch"] - row["commit_end"]) / 1e6,
                        (row["dispatch"] - row["commit_begin"]) / 1e6],
                    "dispatch_to_first_event_ms": (row["first_event"] - row["dispatch"]) / 1e6,
                    "accepted_to_terminal_ms": (row["terminal"] - row["accepted"]) / 1e6,
                    "terminal_to_durable_ms": (row["durable"] - row["terminal"]) / 1e6,
                    "terminal_to_projected_ms": (row["projected"] - row["terminal"]) / 1e6})
        return {"samples": samples, "missing_observations": dict(missing), "overflow": self.overflow,
            "snapshots": self.snapshots, "suppressed_duplicate_http_requests": self.duplicate_http_requests,
            "shutdown_ms": self.shutdown_ms,
            "scope": "Isolated explicit command workload; snapshot zeros are observations, not coverage of fault/retry/relay workloads. No IDs/payloads/paths exported as metric labels. First event is observed at journal ingress, not the OS read boundary; accepted is native started evidence. Commit timestamp is bounded by COMMIT call/return. Timing includes probe overhead; not a comparable performance benchmark."}
