"""Measure the actual HOME projection over disposable, migrated SQLite data.

No provider, server, credential or production home is used. This measures the
service and JSON encoding; it deliberately does not claim HTTP/browser latency.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import tempfile
from time import perf_counter

from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.domain.runtime_context import RuntimeRequestContext


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = RuntimeRequestContext(None, "http_loopback", trusted_local_operator=True)
WORKSPACE = "home-performance-synthetic"


def percentiles(values):
    ordered = sorted(values)
    return dict(p50_ms=statistics.median(ordered),
                p95_ms=ordered[math.ceil(.95 * len(ordered)) - 1])


class MeasuredFactory:
    """Observe the real UoW, rejecting SQL writes while a GET is measured."""
    def __init__(self, factory):
        self.factory = factory
        self.statements = []
        self.transactions = 0
        self.changes = 0
        self.plans = {}
        self.collect_plans = False

    @contextmanager
    def unit_of_work(self, *, write=True):
        assert write is False, "Home must request a read UoW"
        self.transactions += 1
        with self.factory.unit_of_work(write=write) as uow:
            connection = uow.connection
            before = connection.total_changes
            queries = []
            connection.set_trace_callback(queries.append)
            mutations = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                         sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE,
                         sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_CREATE_INDEX,
                         sqlite3.SQLITE_DROP_INDEX}
            connection.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY
                                      if action in mutations else sqlite3.SQLITE_OK)
            try:
                yield uow
            finally:
                connection.set_trace_callback(None)
                connection.set_authorizer(None)
                self.changes += connection.total_changes - before
                self.statements.extend(queries)
                if self.collect_plans:
                    for statement in queries:
                        if statement.lstrip().split(None, 1)[0].upper() not in {"SELECT", "WITH"}:
                            continue
                        identity = hashlib.sha256(statement.encode()).hexdigest()
                        if identity in self.plans:
                            continue
                        try:
                            plan = [tuple(row) for row in connection.execute(
                                "EXPLAIN QUERY PLAN " + statement)]
                            self.plans[identity] = dict(sql_sha256=identity, plan=plan)
                        except sqlite3.Error as error:
                            # UDFs have already been removed by the source's
                            # bounded reader. Record the limitation explicitly.
                            self.plans[identity] = dict(sql_sha256=identity,
                                                       unavailable=type(error).__name__)


def seed(deps, agents, activities, events):
    """Count actual workers separately from the seeded human operator.

    Every worker has an explicit workspace session, so the selected scope really
    contains 1/10/100 workers even when it contains fewer productive handoffs.
    These legacy presence sessions do not claim native execution.
    """
    names = [f"perf-agent-{index:03d}" for index in range(agents)]
    now = deps.clock.now_iso()
    started = perf_counter()
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=WORKSPACE)
        for agent in names:
            deps.repos.agents.upsert(uow, agent_id=agent, role="worker")
            deps.repos.sessions.create(uow, session_id=f"session-{agent}", agent_id=agent,
                                       workspace_id=WORKSPACE, status="active")
        uow.connection.executemany(
            "INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ((f"perf-handoff-{index:05d}", WORKSPACE, names[index % agents],
              '{"strategy":"broadcast"}', "eligible", "OPEN", now, now)
             for index in range(activities)))
        uow.connection.executemany(
            "INSERT INTO events(workspace_id,stream,type,actor_agent_id,payload,visibility,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            ((WORKSPACE, "home-performance", "fixture.performance", names[index % agents],
              '{"synthetic":true}', "public", now) for index in range(events)))
    elapsed = (perf_counter() - started) * 1000
    with deps.connection_factory.unit_of_work(write=False) as uow:
        counts = {table: uow.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("agents", "handoffs", "events", "sessions", "execution_operations")}
        counts["worker_agents"] = uow.connection.execute("SELECT COUNT(*) FROM agents WHERE agent_id<>'operator'").fetchone()[0]
    assert counts["agents"] == agents + 1 and counts["worker_agents"] == agents
    assert counts["sessions"] == agents and counts["handoffs"] == activities and counts["events"] == events
    return counts, elapsed


def measure_case(home, *, agents, activities, events, samples):
    started = perf_counter()
    deps = bootstrap({"OKTO_NEXUS_EMBEDDING_MODE": "off", "OKTO_NEXUS_TELEMETRY_ENABLED": "0"},
                     ["--home", str(home)])
    boot_ms = (perf_counter() - started) * 1000
    try:
        return measure_dependencies(deps, agents=agents, activities=activities,
                                    events=events, samples=samples, boot_ms=boot_ms)
    finally:
        deps.connection_factory.close()


def measure_dependencies(deps, *, agents, activities, events, samples, boot_ms):
    counts, seed_ms = seed(deps, agents, activities, events)
    service = build_app(deps).state.home
    measured = MeasuredFactory(deps.connection_factory)
    service.factory = measured

    def read():
        return service.read(context=OPERATOR, filters={"workspace_id": WORKSPACE})

    measured.collect_plans = True
    started = perf_counter()
    cold = read()
    first_read_ms = (perf_counter() - started) * 1000
    measured.collect_plans = False
    # First query includes plan collection; only steady samples below are timed.
    # This is process-first, not an OS page-cache cold experiment.
    measured.statements.clear()
    measured.transactions = 0
    warm, encoding, sizes, queries, transactions = [], [], [], [], []
    value = cold
    for _ in range(samples):
        query_before, transaction_before = len(measured.statements), measured.transactions
        started = perf_counter()
        value = read()
        warm.append((perf_counter() - started) * 1000)
        started = perf_counter()
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        encoding.append((perf_counter() - started) * 1000)
        sizes.append(len(payload))
        queries.append(len(measured.statements) - query_before)
        transactions.append(measured.transactions - transaction_before)
    assert measured.changes == 0 and all(count == 1 for count in transactions)
    assert value["work"]["status"] == "ready", value["work"]
    assert value["agents"]["total"] == agents
    assert value["work"]["total"] == activities
    assert len(value["work"]["items"]) == min(10, activities)
    # The event journal is never embedded in this overview.
    assert "fixture.performance" not in json.dumps(value)
    pages, seen, cursor = 1, {item["id"] for item in value["work"]["items"]}, value["work"]["next_cursor"]
    while cursor:
        page = service.read(context=OPERATOR, filters={"workspace_id": WORKSPACE},
                            section="work", cursor=cursor, limit=100)
        assert page["total"] == activities
        ids = {item["id"] for item in page["items"]}
        assert seen.isdisjoint(ids)
        seen |= ids
        pages += 1
        cursor = page["next_cursor"]
    assert len(seen) == activities
    return dict(dataset=counts, bootstrap_ms=boot_ms, seed_transaction_ms=seed_ms,
                first_service_read_with_explain_ms=first_read_ms,
                cold_cache_claimed=False, discarded_warmups=1, samples=samples,
                service_read=percentiles(warm), json_encoding=percentiles(encoding),
                sql_statements_min=min(queries), sql_statements_max=max(queries),
                transactions_per_read=sorted(set(transactions)), database_changes=measured.changes,
                payload_bytes_min=min(sizes), payload_bytes_max=max(sizes),
                sections={key: value[key]["status"] for key in
                          ("work", "attention", "results", "agents", "external_activity")},
                pagination=dict(pages=pages, distinct_activities=len(seen)),
                explain_query_plans=list(measured.plans.values()),
                provider_called=False, http_measured=False, browser_measured=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--ram-bytes", type=int, help="Measured physical RAM; metadata only")
    parser.add_argument("--environment-note", default="", help="Concurrent load/cache limitations")
    parser.add_argument("--quick", action="store_true", help="Only the single-agent smoke dataset")
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("At least two samples are required")
    cases = [(1, 10, 100)] if args.quick else [(1, 10, 100), (10, 10, 100),
                                             (100, 10, 100), (100, 1000, 100000)]
    results = []
    with tempfile.TemporaryDirectory(prefix="nexus-home-r1-performance-") as temporary:
        for index, (agents, activities, events) in enumerate(cases):
            result = measure_case(Path(temporary) / f"case-{index}", agents=agents,
                                  activities=activities, events=events, samples=args.samples)
            results.append(result)
            print(json.dumps({key: result[key] for key in ("dataset", "service_read", "sql_statements_max",
                                                          "payload_bytes_max")}), flush=True)
    sources = ["scripts/measure_home_evolution.py", "pyproject.toml", "uv.lock",
               "src/okto_nexus/application/home.py", "src/okto_nexus/domain/home.py",
               "src/okto_nexus/adapters/outbound/sqlite/home.py",
               "src/okto_nexus/adapters/inbound/http/home.py"]
    evidence = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(),
                    environment=dict(os=platform.platform(), machine=platform.machine(),
                                     processor=platform.processor(), cpu_logical=os.cpu_count(),
                                     ram_bytes=args.ram_bytes, note=args.environment_note,
                                     python=platform.python_version(), sqlite=sqlite3.sqlite_version),
                    input_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                  for name in sources if (ROOT / name).is_file()},
                    cases=results,
                    limitations=["Synthetic open handoffs; no native/provider execution.",
                                 "Service/SQLite + JSON only; HTTP, render, realtime rate measured separately.",
                                 "First query is not a controlled OS cold-cache measurement.",
                                 "EXPLAIN recorded before any proposed index change; no index added by this tool."])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
