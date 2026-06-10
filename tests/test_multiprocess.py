"""Cross-PROCESS concurrency tests over one shared WAL nexus.db.

The deploy model is N processes (MCP stdio servers + CLI tail) over a single
SQLite database in WAL mode; every other concurrency test in this suite is
thread-based inside one process. Here we spawn REAL Python processes
(``subprocess.Popen([sys.executable, worker.py, ...])``) that each run the
package's fail-closed ``bootstrap()`` (real config, real ConnectionFactory
PRAGMAs, real migrations, real services, real SystemClock - no test doubles)
against a shared temporary home, and exercise the two concurrency hinges:

* ``handoff_claim``: N processes dispute one OPEN handoff - exactly one wins,
  every loser gets the business error (``HANDOFF_ALREADY_CLAIMED``, never an
  opaque ``DB_ERROR``), and the row records the winner only;
* ``inbox_pull``: N processes drain the SAME recipient's inbox - no delivery
  is handed to two processes within its lease, and none is lost.

Plus the cross-process guarantees those hinges rest on: ``busy_timeout``
absorbing writer contention BETWEEN processes (every concurrent writer exits
cleanly; all events commit with strictly monotonic ``event_id``), and the
ADR 0001 at-least-once lease/ack cycle surviving a REAL process death
(``os._exit`` after pull, no ack -> redelivery once the lease expires).

Workers synchronise their hot call through ready/start sentinel files so the
racing calls genuinely overlap. Every wait is bounded so CI can never hang.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.handoff import (
    build_service as build_handoff_service,
)
from okto_nexus.adapters.inbound.mcp.tools.inbox import (
    build_service as build_inbox_service,
)
from okto_nexus.domain.handoff import EVENT_CREATED, STATUS_CLAIMED
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.domain.inbox import (
    DELIVERY_DELIVERED,
    DELIVERY_UNREAD,
    new_delivery_id,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Bound for every cross-process wait (ready handshake, join, hot call).
JOIN_TIMEOUT_SECONDS = 30.0

#: Canonical fixed-width ISO instant safely in the past (lease comparisons are
#: lexicographic on this shape), used to force expiry instead of sleeping.
PAST_ISO = "2020-01-01T00:00:00.000000Z"

# The worker program executed by each spawned process. Kept as source written
# to tmp_path (not a pickled function): spawn-safe on Windows under pytest and
# free of -c quoting. It uses ONLY the real package surface via bootstrap().
WORKER_SOURCE = '''\
"""Cross-process worker for tests/test_multiprocess.py (written at test time).

Runs one bus operation through the real package bootstrap against the shared
nexus.db named by OKTO_NEXUS_HOME. Synchronises the hot call with sibling
processes via ready/start sentinel files. Exit codes: 0 = clean (including an
EXPECTED business error, reported in the JSON line on stdout); 1 = deliberate
hard death (pull_then_die); 7 = an exception LEAKED out of the service call
(e.g. SQLITE_BUSY surfacing as DB_ERROR); 8 = unknown mode; 9 = start-sentinel
timeout.
"""
import json
import os
import sys
import time


def _emit(obj):
    print(json.dumps(obj), flush=True)


def _ready_then_wait(ready_path, start_path, timeout=30.0):
    open(ready_path, "w").close()
    deadline = time.monotonic() + timeout
    while not os.path.exists(start_path):
        if time.monotonic() >= deadline:
            _emit({"fatal": "timed out waiting for the start sentinel"})
            os._exit(9)
        time.sleep(0.005)


def _deps():
    from okto_nexus.adapters.inbound.mcp.server import bootstrap

    return bootstrap(os.environ, [])


def main(argv):
    mode, ready, start, rest = argv[0], argv[1], argv[2], argv[3:]
    from okto_nexus.errors import OktoNexusError

    deps = _deps()
    if mode == "claim":
        from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service

        project_root, handoff_id, agent_id = rest
        service = build_service(deps)
        _ready_then_wait(ready, start)
        try:
            out = service.handoff_claim(
                project_root=project_root, handoff_id=handoff_id, agent_id=agent_id
            )
            _emit({"outcome": "claimed", "claimed_by": out["claimed_by"]})
        except OktoNexusError as exc:
            _emit({"outcome": "error", "code": exc.code, "retryable": exc.retryable})
        return 0
    if mode == "pull_until_empty":
        from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service

        (agent_id,) = rest
        service = build_service(deps)
        _ready_then_wait(ready, start)
        pulled = []
        while True:
            page = service.pull(agent_id=agent_id, limit=1)
            if page["count"] == 0:
                break
            pulled.extend(m["message_id"] for m in page["messages"])
        _emit({"pulled": pulled})
        return 0
    if mode == "pull_then_die":
        from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service

        (agent_id,) = rest
        service = build_service(deps)
        _ready_then_wait(ready, start)
        page = service.pull(agent_id=agent_id)
        _emit({"pulled": [m["message_id"] for m in page["messages"]]})
        os._exit(1)  # hard death: lease stamped, never acked, no teardown
    if mode == "create_handoffs":
        from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service

        project_root, agent_id, count = rest[0], rest[1], int(rest[2])
        service = build_service(deps)
        _ready_then_wait(ready, start)
        created = [
            service.handoff_create(
                project_root=project_root,
                from_agent_id=agent_id,
                target={"strategy": "broadcast"},
                visibility="public",
            )["handoff_id"]
            for _ in range(count)
        ]
        _emit({"created": created})
        return 0
    _emit({"fatal": "unknown mode: " + mode})
    return 8


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(7)
'''


# --------------------------------------------------------------------------- #
# Fixture & helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def xproc(tmp_path):
    """A migrated shared home + the worker script + a child-process env.

    The parent's ``deps`` come from the same real ``bootstrap()`` the workers
    call, pointed at the same ``OKTO_NEXUS_HOME``; the env hands children the
    repo's ``src/`` on PYTHONPATH so every process imports ONE source tree.
    """
    home = tmp_path / "okto_home"
    deps = bootstrap({"OKTO_NEXUS_HOME": str(home)}, [])
    worker = tmp_path / "xproc_worker.py"
    worker.write_text(WORKER_SOURCE, encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()

    env = {k: v for k, v in os.environ.items() if not k.startswith("OKTO_NEXUS_")}
    env["OKTO_NEXUS_HOME"] = str(home)
    src = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing

    return SimpleNamespace(
        deps=deps,
        worker=worker,
        project=str(project),
        env=env,
        tmp=tmp_path,
    )


def _spawn(x, mode, idx, *args):
    """Start one worker process; returns ``(Popen, ready_sentinel_path)``."""
    ready = x.tmp / f"ready-{mode}-{idx}"
    start = x.tmp / "start"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(x.worker),
            mode,
            str(ready),
            str(start),
            *[str(a) for a in args],
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=x.env,
    )
    return proc, ready


def _run_to_completion(x, procs_readies, timeout=JOIN_TIMEOUT_SECONDS):
    """Barrier-release all workers, join them, return ``[(rc, out, err)]``.

    Waits for every worker's ready sentinel, then creates the shared start
    sentinel so the hot calls fire together. Every wait is bounded; any
    still-running worker is killed on the way out so the suite never hangs.
    """
    procs = [p for p, _ in procs_readies]
    try:
        deadline = time.monotonic() + timeout
        pending = list(procs_readies)
        while pending:
            pending = [(p, r) for (p, r) in pending if not r.exists()]
            for proc, ready in pending:
                if proc.poll() is not None and not ready.exists():
                    out, err = proc.communicate()
                    raise AssertionError(
                        f"worker died before signalling ready "
                        f"(rc={proc.returncode}); stdout={out!r} stderr={err!r}"
                    )
            if pending and time.monotonic() >= deadline:
                raise AssertionError("workers never signalled ready")
            if pending:
                time.sleep(0.005)
        (x.tmp / "start").write_text("go", encoding="utf-8")
        results = []
        for proc in procs:
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()
                raise AssertionError(
                    f"worker hung past {timeout}s; stdout={out!r} stderr={err!r}"
                ) from None
            results.append((proc.returncode, out, err))
        return results
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()


def _assert_clean_exit(results):
    for rc, out, err in results:
        assert rc == 0, (
            f"worker leaked a failure across the process boundary (rc={rc}); "
            f"stdout={out!r} stderr={err!r}"
        )


def _payload(out, err):
    lines = [line for line in out.splitlines() if line.strip()]
    assert lines, f"worker produced no report; stderr:\n{err}"
    return json.loads(lines[-1])


def _seed_workspace(x):
    ws = resolve_workspace_id(x.project)
    with x.deps.connection_factory.unit_of_work() as uow:
        x.deps.repos.workspaces.upsert(
            uow,
            workspace_id=ws,
            root_realpath=os.path.realpath(x.project),
            last_seen_at=x.deps.clock.now_iso(),
        )
    return ws


def _register_agents(x, agent_ids):
    with x.deps.connection_factory.unit_of_work() as uow:
        for agent_id in agent_ids:
            x.deps.repos.agents.upsert(uow, agent_id=agent_id)


def _seed_unread(x, workspace_id, recipient, message_ids):
    """Queue one unread delivery per message_id for ``recipient`` (real repos)."""
    now = x.deps.clock.now_iso()
    with x.deps.connection_factory.unit_of_work() as uow:
        for message_id in message_ids:
            x.deps.repos.messages.create(
                uow,
                message_id=message_id,
                workspace_id=workspace_id,
                from_agent_id="sender",
                subject="subj",
                body=f"body of {message_id}",
            )
            x.deps.repos.deliveries.create(
                uow,
                delivery_id=new_delivery_id(),
                message_id=message_id,
                recipient_agent_id=recipient,
                status=DELIVERY_UNREAD,
                created_at=now,
            )


def _rows(x, sql, params=()):
    conn = x.deps.connection_factory.get_connection()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Hinge 1: handoff_claim disputed by N processes
# --------------------------------------------------------------------------- #
def test_handoff_claim_race_across_processes_single_winner(xproc):
    """Three OS processes claim one OPEN handoff simultaneously: exactly one
    wins; both losers exit 0 carrying HANDOFF_ALREADY_CLAIMED (a business
    error, never DB_ERROR); the row holds the winner with a live lease."""
    _seed_workspace(xproc)
    racers = ["racer-0", "racer-1", "racer-2"]
    _register_agents(xproc, ["creator", *racers])
    service = build_handoff_service(xproc.deps)
    hid = service.handoff_create(
        project_root=xproc.project,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    procs = [
        _spawn(xproc, "claim", i, xproc.project, hid, agent)
        for i, agent in enumerate(racers)
    ]
    results = _run_to_completion(xproc, procs)

    _assert_clean_exit(results)
    outcomes = [_payload(out, err) for _, out, err in results]
    wins = [o for o in outcomes if o.get("outcome") == "claimed"]
    losses = [o for o in outcomes if o.get("outcome") == "error"]
    assert len(wins) == 1 and len(losses) == len(racers) - 1, outcomes
    assert {loss["code"] for loss in losses} == {"HANDOFF_ALREADY_CLAIMED"}
    assert all(loss["code"] != "DB_ERROR" for loss in losses)

    # Zero corruption: the row records exactly the reported winner, CLAIMED,
    # under a lease.
    (row,) = _rows(
        xproc,
        "SELECT status, claimed_by, lease_expires_at FROM handoffs "
        "WHERE handoff_id = ?",
        (hid,),
    )
    assert row["status"] == STATUS_CLAIMED
    assert row["claimed_by"] == wins[0]["claimed_by"]
    assert row["claimed_by"] in racers
    assert row["lease_expires_at"] is not None


# --------------------------------------------------------------------------- #
# Hinge 2: inbox_pull of the SAME recipient by N processes
# --------------------------------------------------------------------------- #
def test_inbox_pull_race_across_processes_each_delivery_to_exactly_one(xproc):
    """Three OS processes drain one recipient's inbox concurrently (limit=1
    pulls for maximal interleaving): no message lands in two processes within
    its lease, none is lost, and every delivery row was claimed exactly once."""
    workspace_id = _seed_workspace(xproc)
    _register_agents(xproc, ["sender", "shared-recipient"])
    message_ids = [f"m-{i:02d}" for i in range(8)]
    _seed_unread(xproc, workspace_id, "shared-recipient", message_ids)

    procs = [
        _spawn(xproc, "pull_until_empty", i, "shared-recipient") for i in range(3)
    ]
    results = _run_to_completion(xproc, procs)

    _assert_clean_exit(results)
    pulls = [_payload(out, err)["pulled"] for _, out, err in results]
    all_pulled = [mid for chunk in pulls for mid in chunk]
    # Exactly-once within the lease: no duplicate across (or within) processes.
    assert sorted(all_pulled) == sorted(set(all_pulled)), pulls
    # ...and nothing was lost: the union covers every seeded message.
    assert set(all_pulled) == set(message_ids), pulls

    rows = _rows(xproc, "SELECT status, attempts FROM message_deliveries")
    assert len(rows) == len(message_ids)
    assert all(row["status"] == DELIVERY_DELIVERED for row in rows)
    # attempts == 1 everywhere: each row was claimed by exactly one pull.
    assert all(row["attempts"] == 1 for row in rows)


# --------------------------------------------------------------------------- #
# ADR 0001 at-least-once against a REAL process death
# --------------------------------------------------------------------------- #
def test_lease_redelivery_after_real_process_death(xproc):
    """A worker pulls (lease stamped) and dies hard via os._exit(1) with no
    ack: while the lease lives the delivery is NOT re-handed out; once the
    lease is forced into the past, the next pull redelivers it."""
    workspace_id = _seed_workspace(xproc)
    _register_agents(xproc, ["sender", "doomed"])
    _seed_unread(xproc, workspace_id, "doomed", ["m-doomed"])

    procs = [_spawn(xproc, "pull_then_die", 0, "doomed")]
    ((rc, out, err),) = _run_to_completion(xproc, procs)
    assert rc == 1, f"worker should die via os._exit(1); stdout={out!r} stderr={err!r}"
    assert _payload(out, err)["pulled"] == ["m-doomed"]

    inbox = build_inbox_service(xproc.deps)
    # Lease still live: the dead process's claim must NOT be re-handed out.
    assert inbox.pull(agent_id="doomed")["count"] == 0

    # Force expiry directly in the store (no sleeping; the worker's real clock
    # stamped a lease minutes in the future).
    with xproc.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE message_deliveries SET lease_expires_at = ? "
            "WHERE message_id = ?",
            (PAST_ISO, "m-doomed"),
        )

    page = inbox.pull(agent_id="doomed")
    assert [m["message_id"] for m in page["messages"]] == ["m-doomed"]
    (row,) = _rows(
        xproc,
        "SELECT status, attempts FROM message_deliveries WHERE message_id = ?",
        ("m-doomed",),
    )
    assert row["status"] == DELIVERY_DELIVERED
    assert row["attempts"] == 2  # first claim died with the process; redelivered once


# --------------------------------------------------------------------------- #
# busy_timeout BETWEEN processes + global event monotonicity
# --------------------------------------------------------------------------- #
def test_concurrent_writer_processes_commit_all_events_monotonically(xproc):
    """Three writer processes burst 6 handoff_create calls each against the
    shared WAL store: every process exits 0 (no SQLITE_BUSY leaked across the
    process boundary), all 18 events commit, and event_id is strictly
    monotonic with one event per created handoff."""
    _seed_workspace(xproc)
    writers = ["writer-0", "writer-1", "writer-2"]
    _register_agents(xproc, writers)
    per_worker = 6

    procs = [
        _spawn(xproc, "create_handoffs", i, xproc.project, agent, per_worker)
        for i, agent in enumerate(writers)
    ]
    results = _run_to_completion(xproc, procs)

    _assert_clean_exit(results)  # exit!=0 would mean a leaked DB_ERROR/BUSY
    created = [
        hid for _, out, err in results for hid in _payload(out, err)["created"]
    ]
    assert len(created) == len(writers) * per_worker
    assert len(set(created)) == len(created)

    rows = _rows(
        xproc,
        "SELECT event_id, payload FROM events WHERE type = ? ORDER BY rowid",
        (EVENT_CREATED,),
    )
    event_ids = [row["event_id"] for row in rows]
    assert len(event_ids) == len(created)
    # Strictly monotonic in append order => unique, never reused or clobbered.
    assert all(b > a for a, b in zip(event_ids, event_ids[1:]))
    payload_ids = {json.loads(row["payload"])["handoff_id"] for row in rows}
    assert payload_ids == set(created)
