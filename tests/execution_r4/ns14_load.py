"""Synthetic identity churn and two authenticated executor senders on one store."""
import asyncio
import json
import os
import platform
import sys
import threading
import time
import traceback
import tracemalloc

from fastapi.testclient import TestClient
from nexus_connector_core import InstallationCandidate, build_executor_inventory_snapshot, R4_PREVIEW_REVISION, encode_r4_frame
from nexus_connector_core.discovery import fingerprint
from okto_nexus.adapters.outbound.sqlite.execution_identity import register_remote_executor
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket, verify_execution_ticket
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.application.execution_dispatch_pump import ExecutionDispatchPump
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.keys import hash_api_key
from test_ns09 import negotiate


def second_executor(state, root):
    deps, app, access, operator, _, channel, _, _ = state
    factory, server = deps.connection_factory, channel.server_id
    executor = register_remote_executor(factory, actor_agent_id="registrar",
        connector_id="load-second", client_intent_id="load-second-register").executor_id
    binary = root / "codex.exe"
    candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary), "explicit", "selected")
    snapshot = build_executor_inventory_snapshot([candidate], server_id=server,
        executor_id=executor, producer_instance_id="load-second", publication_sequence=1)
    candidate_ref = snapshot["evidence"][0]["candidate_ref"]
    revision = snapshot["inventory_revision"]
    def copy(conn, table, where, args, **changes):
        row = dict(conn.execute("SELECT * FROM " + table + " WHERE " + where, args).fetchone())
        row.update(changes)
        conn.execute("INSERT INTO " + table + "(" + ",".join(row) + ") VALUES(" +
                     ",".join("?" for _ in row) + ")", tuple(row.values()))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        copy(conn, "agent_endpoints", "endpoint_id='ep'", (), endpoint_id="ep-load-second", agent_id="other")
        copy(conn, "execution_workspace_bindings", "executor_id=?", (channel.executor_id,),
             executor_id=executor, workspace_binding_id="wxb-load-second")
        copy(conn, "execution_realizations", "executor_id=?", (channel.executor_id,),
             executor_id=executor, workspace_binding_id="wxb-load-second", subject_agent_id="other",
             candidate_ref=candidate_ref, inventory_revision=revision)
        copy(conn, "execution_bindings", "executor_id=?", (channel.executor_id,),
             executor_id=executor, binding_id="binding-load-second", endpoint_id="ep-load-second",
             workspace_binding_id="wxb-load-second", candidate_ref=candidate_ref, inventory_revision=revision)
        copy(conn, "execution_inventory_snapshots", "executor_id=?", (channel.executor_id,),
             executor_id=executor, publication_sequence=1, inventory_revision=revision, canonical_projection=json.dumps(snapshot),
             producer_instance_id="load-second")
        copy(conn, "execution_inventory_current", "executor_id=?", (channel.executor_id,),
             executor_id=executor, publication_sequence=1, inventory_revision=revision)
    app.state.inventory_fresh_publications[(server, executor)] = (1, time.monotonic(), 0)
    access.issue(operator, actor_agent_id="other", endpoint_id="ep-load-second",
                 actions=["open", "send", "interrupt", "close"],
                 expires_at=iso_plus(deps.clock.now_iso(), 3600))
    _, revisions, _ = current_agent_revisions(factory, agent_id="other")
    lane = issue_execution_ticket(factory, server_id=server, executor_id=executor,
        binding_id="binding-load-second", agent_id="other",
        scopes=frozenset({"lane:attach", "lease:request"})).ticket
    link = issue_execution_ticket(factory, server_id=server, executor_id=executor,
        binding_id=None, agent_id="registrar").ticket
    return executor, revisions, lane, link


def refresh_inventory(state, root, client):
    deps, app, _, _, _, channel, _, _ = state
    binary = root / "codex.exe"
    candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary), "explicit", "selected")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        current = uow.connection.execute(
            "SELECT publication_sequence,inventory_revision FROM execution_inventory_current "
            "WHERE server_id=? AND executor_id=?", (channel.server_id, channel.executor_id)).fetchone()
    refreshed = build_executor_inventory_snapshot([candidate], server_id=channel.server_id,
        executor_id=channel.executor_id, producer_instance_id=channel.connection_id,
        publication_sequence=current["publication_sequence"] + 1)
    assert refreshed["inventory_revision"] == current["inventory_revision"]
    published = client.put(f"/v1/runtime/executors/{channel.executor_id}/inventory",
        headers={"Authorization": "Bearer " + app.state.test_opening_ticket}, json=refreshed)
    assert published.status_code == 200, published.text
    assert published.json()["publication_sequence"] == current["publication_sequence"] + 1
    assert published.json()["fresh_for_ms"] > 0


def run_load(state, root, record_property):
    deps, app, access, _, _, first, opened, _ = state
    factory = deps.connection_factory
    client = TestClient(app, base_url="https://127.0.0.1:8202")
    auth = app.state.auth
    async def executor_snapshot():
        # Test-only introspection of the actual CPython executor. Its lazy
        # expansion is bounded by its configured capacity, not a +4 heuristic.
        pool = asyncio.get_running_loop()._default_executor
        assert pool is not None
        return dict(identity=id(pool), limit=pool._max_workers,
                    threads=[thread.ident for thread in pool._threads])
    def pool_snapshot():
        return app.state.test_opening_socket.portal.call(executor_snapshot)
    now = deps.clock.now_iso()
    count = 100_000
    last_heartbeat = 0.0
    last_maintenance = time.monotonic()
    lease_serial = 1  # decision_state applied the initial fixture lease.
    def heartbeat(*, maintain=False):
        nonlocal last_heartbeat, last_maintenance, lease_serial
        if time.monotonic() - last_heartbeat >= 5:
            app.state.test_opening_socket.send_text(encode_r4_frame(dict(
                protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type="heartbeat",
                server_id=first.server_id, executor_id=first.executor_id,
                connection_id=first.connection_id,
                connection_generation=first.connection_generation)).decode())
            last_heartbeat = time.monotonic()
        if maintain or time.monotonic() - last_maintenance >= 30:
            refresh_inventory(state, root, client)
            ws = app.state.test_opening_socket
            renewal = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
                type="lease.renew", request_id=f"load-renew-{lease_serial}",
                grant_id=state[4]["grant_id"], expected_lease_serial=lease_serial,
                purpose="renew", scope=opened["scope"], connection_id=first.connection_id,
                connection_generation=first.connection_generation)
            raw = encode_r4_frame(renewal).decode()
            ws.send_text(raw)
            granted = ws.receive_json()
            assert granted["type"] == "lease.granted", granted
            assert granted["request_id"] == renewal["request_id"]
            assert granted["scope"] == opened["scope"]
            assert granted["lease_serial"] == lease_serial + 1
            ack = {key: granted[key] for key in ("protocol_major", "contract_revision", "request_id",
                "grant_id", "lease_id", "lease_serial", "scope")}
            ack.update(type="lease.applied", application_stage="RENEWED",
                connection_id=first.connection_id, connection_generation=first.connection_generation)
            ws.send_text(encode_r4_frame(ack).decode())
            # Sequential wire replay observes the preceding ACK commit. It must
            # return the same grant, not create another lease or extend expiry.
            ws.send_text(raw)
            assert ws.receive_json() == granted
            with factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute("SELECT status,lease_serial FROM execution_leases WHERE lease_id=?",
                    (granted["lease_id"],)).fetchone()
                assert tuple(row) == ("ACTIVE", lease_serial + 1)
            lease_serial += 1
            last_maintenance = time.monotonic()
    heartbeat()
    for offset in range(0, count, 500):
        heartbeat()
        with factory.unit_of_work() as uow:
            uow.connection.executemany("INSERT INTO agents(agent_id,created_at,api_key_hash,is_active) VALUES(?,?,?,1)",
                ((f"load-{i}", now, hash_api_key("nxs_" + format(i, "048x"))) for i in range(offset, offset + 500)))
        time.sleep(.001)
    threads_before_snapshot = [(t.ident, t.name) for t in threading.enumerate()]
    pool_before = pool_snapshot()
    samples = []
    write_batches = []
    started = time.perf_counter()
    tracemalloc.start()
    try:
        for offset in range(0, count, 500):
            heartbeat()
            requested = time.perf_counter()
            with factory.unit_of_work() as uow:
                acquired = time.perf_counter()
                for i in range(offset, offset + 500):
                    assert auth.resolve(uow, "nxs_" + format(i, "048x")).agent_id == f"load-{i}"
            write_batches.append((acquired - requested, time.perf_counter() - acquired))
            if (offset + 500) % 25_000 == 0:
                current, peak = tracemalloc.get_traced_memory()
                samples.append(dict(identities=offset + 500, current_bytes=current, peak_bytes=peak,
                                    cache_entries=auth.cache_stats()["entries"]))
                assert auth.cache_stats()["entries"] == 4096
    finally:
        tracemalloc.stop()
        # Preserve bounded timing evidence even if a later heartbeat finds a
        # closed channel. Do not turn lock contention into a read-only touch.
        record_property("identity_write_batches", json.dumps(dict(
            completed=len(write_batches), identities_per_batch=500,
            max_acquire_seconds=max((row[0] for row in write_batches), default=0),
            max_held_seconds=max((row[1] for row in write_batches), default=0),
            total_acquire_seconds=sum(row[0] for row in write_batches),
            total_held_seconds=sum(row[1] for row in write_batches))))
    identity_seconds = time.perf_counter() - started
    assert samples[-1]["current_bytes"] < samples[0]["current_bytes"] * 1.5 + 524288
    threads_after_snapshot = [(t.ident, t.name) for t in threading.enumerate()]
    pool_after = pool_snapshot()
    frames = sys._current_frames()
    before_ids = {ident for ident, _ in threads_before_snapshot}
    new_stacks = {str(ident): [(os.path.basename(frame.filename), frame.name, frame.lineno)
                              for frame in traceback.extract_stack(frames[ident])]
                  for ident, _ in threads_after_snapshot if ident not in before_ids and ident in frames}
    del frames
    record_property("identity_threads", json.dumps(dict(
        before=threads_before_snapshot, after=threads_after_snapshot, new_stacks=new_stacks,
        pool_before=pool_before, pool_after=pool_after)))
    assert pool_after["identity"] == pool_before["identity"]
    assert pool_after["limit"] == pool_before["limit"]
    assert len(pool_after["threads"]) <= pool_after["limit"]
    outside_before = {ident for ident, _ in threads_before_snapshot} - set(pool_before["threads"])
    outside_after = {ident for ident, _ in threads_after_snapshot} - set(pool_after["threads"])
    assert len(outside_after - outside_before) <= 4
    with factory.unit_of_work(write=False) as uow:
        plan = [r[3] for r in uow.connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM agents WHERE api_key_hash=? AND is_active=1",
            (hash_api_key("nxs_" + format(0, "048x")),))]
    assert any("SEARCH" in line and "INDEX" in line for line in plan)

    # The synthetic peer must maintain its real authority during a slow load,
    # just as an executor does. Neither inventory nor lease TTL is extended.
    heartbeat(maintain=True)
    record_property("load_lease_serial", lease_serial)
    executor, revisions, lane, link = second_executor(state, root)
    from okto_nexus.adapters.inbound.http import executor_link
    info = executor_link.protocol_info()
    def request(actor, intent_id, action, *, second=False):
        body = dict(client_intent_id=intent_id, intent=action,
            binding_id="binding-load-second" if second else "binding",
            workspace_binding_id="wxb-load-second" if second else "wxb")
        if action == "runtime.start":
            body["new_session"] = True
        else:
            body["session_id"] = opened["scope"]["session_id"]
            if action == "turn.submit":
                body["text"] = "Synthetic load request"
        headers = {"Authorization": "Bearer " + app.state.test_agent_keys[actor]}
        result = client.post("/v1/runtime/intents:resolve", headers=headers, json=body)
        assert result.status_code == 200, result.text
        resolved = result.json()
        assert resolved["can_submit"], resolved["blockers"]
        result = client.post("/v1/runtime/operations", headers=headers,
            json={k: resolved[k] for k in ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")})
        return result, resolved

    with client.websocket_connect(f"wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link",
            headers={"Authorization": "Bearer " + link}, subprotocols=["nxl.v1"]) as ws:
        second = negotiate(ws, info, revisions, lane, first.server_id, executor,
                           binding_id="binding-load-second", agent_id="other")
        accepted = 0
        for i in range(33):
            response, _ = request("subject", f"load-fill-{i}", "turn.submit")
            if response.status_code == 429:
                break
            assert response.status_code == 202, response.text
            accepted += 1
        assert accepted == 30 and response.status_code == 429
        second_response, second_intent = request("other", "load-second-open", "runtime.start", second=True)
        assert second_response.status_code == 202, second_response.text

        async def exercise():
            sent, closed = [], asyncio.Event()
            def make(channel):
                ticket = issue_execution_ticket(factory, server_id=channel.server_id,
                    executor_id=channel.executor_id, binding_id=None, agent_id="registrar").ticket
                def verify():
                    verify_execution_ticket(factory, ticket=ticket, server_id=channel.server_id,
                                            executor_id=channel.executor_id, scope="link:connect")
                async def send(frame):
                    sent.append((time.perf_counter(), frame))
                    # Synthetic peer retains all ACKs: productive dispatch saturates.
                async def close():
                    closed.set()
                return ExecutionDispatchPump(factory=factory, channel=channel, access=access,
                    fresh_publications=app.state.inventory_fresh_publications, send=send,
                    send_lock=asyncio.Lock(), verify_link=verify, close_link=close, poll_interval=.01)
            pumps = [make(first), make(second)]
            dispatch_started = time.perf_counter()
            for pump in pumps:
                pump.start()
            try:
                async with asyncio.timeout(10):
                    while not any(frame["operation_id"] == second_intent["operation_id"] for _, frame in sent):
                        assert not closed.is_set()
                        await asyncio.sleep(.01)
                second_time = next(stamp for stamp, frame in sent
                    if frame["operation_id"] == second_intent["operation_id"])
                async with asyncio.timeout(10):
                    while sum(frame["executor_id"] == first.executor_id for _, frame in sent) < 3:
                        assert not closed.is_set()
                        await asyncio.sleep(.01)
                control_started = time.perf_counter()
                response, control = await asyncio.to_thread(request, "subject", "load-control", "runtime.close")
                assert response.status_code == 202, response.text
                rejected = 0
                for i in range(20):
                    response, _ = await asyncio.to_thread(request, "subject", f"load-overflow-{i}", "turn.submit")
                    assert response.status_code == 429, response.text
                    rejected += 1
                async with asyncio.timeout(10):
                    while not any(frame["operation_id"] == control["operation_id"] for _, frame in sent):
                        assert not closed.is_set()
                        await asyncio.sleep(.01)
                control_time = next(stamp for stamp, frame in sent if frame["operation_id"] == control["operation_id"])
                assert not closed.is_set()
                assert len({frame["operation_id"] for _, frame in sent}) == len(sent)
                metrics = await asyncio.to_thread(lambda: client.get("/api/v1/metrics/local/summary",
                    headers={"Authorization": "Bearer " + app.state.test_agent_keys["operator"]}).json()["data"])
                assert metrics["runtime_capacity"]["pending_totals"]["regular"]["items"] == 33
                assert metrics["runtime_capacity"]["dispatch_totals"]["regular"]["items"] <= 8
                assert metrics["runtime_capacity"]["dispatch_totals"]["control"]["items"] == 1
                return dict(rejected_during_progress=rejected, sent_frames=len(sent),
                            control_latency_seconds=control_time-control_started,
                            second_executor_latency_seconds=second_time-dispatch_started,
                            gauges=metrics["runtime_capacity"])
            finally:
                for pump in pumps:
                    await pump.stop()
        queue_result = asyncio.run(exercise())
    record_property("ns14_load", json.dumps(dict(identities=count, identity_seconds=identity_seconds,
        memory=samples, query_plan=plan, logical_cpus=os.cpu_count(), processor=platform.processor(),
        platform=platform.platform(), topology="One real SQLite store; public HTTP/WSS authority; real dispatch pumps with synthetic send sinks withholding ACKs.", **queue_result)))
