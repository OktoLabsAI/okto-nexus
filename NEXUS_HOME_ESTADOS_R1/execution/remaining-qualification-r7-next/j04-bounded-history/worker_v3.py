"""PREPARED: installed functional history probe, not a latency benchmark."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PERF = REPO / "NEXUS_HOME_ESTADOS_R1/execution/performance-hst"
MARKER = "J04_FULL_PAYLOAD_NOT_METADATA_6e16f22c"
LARGE = "synthetic-preview-only\n" + "x" * 8192 + MARKER + "z" * 122880


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    assert not path.exists()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def augment(factory, root, clock):
    """Only a copied SQL synthetic dataset; never native/authority qualification."""
    with factory.unit_of_work() as uow:
        conn = uow.connection
        original_open = conn.execute("SELECT count(*) FROM execution_operations WHERE operation_id LIKE 'hst-perf-turn-%' AND admission_state='ACCEPTED'").fetchone()[0]
        assert original_open == 1000
        assert conn.execute("SELECT count(*) FROM execution_event_ingress WHERE session_id LIKE 'hst-perf-session-%'").fetchone()[0] == 100000
        templates = conn.execute("SELECT * FROM execution_operations WHERE operation_id LIKE 'hst-perf-turn-%' ORDER BY operation_id LIMIT 25").fetchall()
        assert len(templates) == 25
        ids = []
        artifacts = root / "synthetic-artifacts"
        artifacts.mkdir()
        for index, row in enumerate(templates):
            operation = dict(row)
            operation.update(operation_id=f"j04-synthetic-terminal-{index:03}", admission_state="RESOLVED_TERMINAL")
            columns = tuple(operation)
            conn.execute("INSERT INTO execution_operations(" + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in columns) + ")", tuple(operation.values()))
            server, executor, oid, session = (operation[key] for key in ("server_id", "executor_id", "operation_id", "session_id"))
            epoch, sequence = conn.execute("SELECT stream_epoch,MAX(sequence) FROM execution_event_ingress WHERE server_id=? AND executor_id=? AND session_id=?", (server, executor, session)).fetchone()
            assert epoch and sequence
            conn.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,native_id,received_at) VALUES(?,?,?,1,?,'SUCCEEDED',1,0,?,?)", (server, executor, oid, operation["intent_hash"], "j04-synthetic-native", clock))
            conn.execute("INSERT INTO execution_results(server_id,executor_id,operation_id,session_id,stream_epoch,terminal_sequence,output_text,output_truncated,output_event_count,delivery_outcome,captured_at) VALUES(?,?,?,?,?,?,?,0,1,'success',?)", (server, executor, oid, session, epoch, sequence, LARGE, clock))
            artifact = f"j04-synthetic-artifact-{index:03}"
            path = artifacts / (artifact + ".txt")
            path.write_text(LARGE, encoding="utf-8")
            conn.execute("INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,content,size_bytes,content_type,created_at) VALUES(?,?,'file',?,?,?,?,'text/plain',?)", (artifact, operation["workspace_id"], artifact + ".txt", str(path), LARGE, len(LARGE.encode()), clock))
            conn.execute("INSERT INTO runtime_results(result_id,payload,publication_state,captured_at,output_text,output_artifact_id,delivery_outcome,canonical_server_id,canonical_executor_id,canonical_operation_id) VALUES(?,?,'PUBLISHED',?,? ,?,'success',?,?,?)", (f"j04-synthetic-result-{index:03}", json.dumps({"synthetic": True, "padding": LARGE}), clock, LARGE, artifact, server, executor, oid))
            ids.append(oid)
        # Preserve event identity/cardinality; these are synthetic history payloads,
        # not a native journal or valid event-hash chain.
        events = conn.execute("SELECT rowid,payload_json FROM execution_event_ingress WHERE session_id LIKE 'hst-perf-session-%' ORDER BY rowid LIMIT 10").fetchall()
        for event in events:
            payload = json.loads(event["payload_json"])
            payload["j04_synthetic_unused_padding"] = LARGE
            conn.execute("UPDATE execution_event_ingress SET payload_json=? WHERE rowid=?", (json.dumps(payload), event["rowid"]))
        assert not list(conn.execute("PRAGMA foreign_key_check"))
        assert conn.execute("SELECT count(*) FROM execution_operations WHERE operation_id LIKE 'hst-perf-turn-%' AND admission_state='ACCEPTED'").fetchone()[0] == 1000
        assert conn.execute("SELECT count(*) FROM execution_event_ingress WHERE session_id LIKE 'hst-perf-session-%'").fetchone()[0] == 100000
    return {"open_activities": 1000, "history_events": 100000, "added_terminal_results": 25,
        "large_event_payloads": 10, "artifact_files": 25, "large_field_bytes": len(LARGE.encode()), "terminal_operation_ids": ids}


def canonical_artifact_paths(factory, home):
    """Metadata only: mirror LocalArtifactStore root, never read file content."""
    storage_root = (home / "artifacts").resolve()
    assert storage_root.is_relative_to(home.resolve())
    expected = {f"j04-synthetic-artifact-{index:03}" for index in range(25)}
    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT artifact_id,storage_path FROM artifacts "
            "WHERE artifact_id LIKE 'j04-synthetic-artifact-%' ORDER BY artifact_id").fetchall()
    assert {row["artifact_id"] for row in rows} == expected and len(rows) == 25
    mapping = []
    for row in rows:
        stored = row["storage_path"]
        assert isinstance(stored, str) and stored and not Path(stored).is_absolute()
        path = (storage_root / stored).resolve()
        assert path.is_relative_to(storage_root) and path != storage_root
        assert path.is_relative_to(home.parent.resolve()) and path.is_file()
        mapping.append({"artifact_id": row["artifact_id"], "storage_path": stored, "canonical_path": str(path)})
    return mapping


@contextmanager
def observe(factory, artifacts, canonical_paths):
    """Row factories return the exact original objects; only metadata is recorded."""
    factory.close()
    original = factory._open_connection
    report = {"rows_materialized": 0, "max_string_bytes": 0, "full_payload_materialized": [], "artifact_content_sql_reads": 0, "artifact_file_reads": []}
    protected_paths = frozenset(Path(item["canonical_path"]).resolve() for item in canonical_paths)
    assert protected_paths and len(canonical_paths) == 25
    report["guarded_artifact_ids"] = 25
    report["guarded_canonical_payload_paths"] = len(protected_paths)

    def opening(*args, **kwargs):
        conn = original(*args, **kwargs)
        row_factory = conn.row_factory

        def row(cursor, values):
            report["rows_materialized"] += 1
            for index, value in enumerate(values):
                if isinstance(value, (str, bytes)):
                    report["max_string_bytes"] = max(report["max_string_bytes"], len(value.encode() if isinstance(value, str) else value))
                    if (MARKER in value if isinstance(value, str) else MARKER.encode() in value):
                        report["full_payload_materialized"].append({"column": cursor.description[index][0], "bytes": len(value)})
            return row_factory(cursor, values) if row_factory else values

        def authorize(action, table, column, database, source):
            if action == sqlite3.SQLITE_READ and table == "artifacts" and column == "content":
                report["artifact_content_sql_reads"] += 1
            return sqlite3.SQLITE_OK

        conn.row_factory = row
        conn.set_authorizer(authorize)
        return conn

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(artifacts) or path in protected_paths:
                report["artifact_file_reads"].append(path.name)
                raise AssertionError("Overview/results must not read artifact content files")

    # Worker ends after the read phase; the hook cannot leak into another app.
    sys.addaudithook(audit)
    factory._open_connection = opening
    try:
        yield report
    finally:
        factory.close()
        factory._open_connection = original


async def exercise(home, clock, benchmark):
    from httpx import ASGITransport, AsyncClient

    from okto_nexus.adapters.inbound.http.app import build_app
    from okto_nexus.bootstrap.dependencies import bootstrap

    fixtures = benchmark.load("j04_clock_only", REPO / "NEXUS_UI_R1/execution/fixtures.py")
    deps = bootstrap({}, ["--home", str(home), "--embedding-mode", "off"])
    deps.clock = fixtures.ControlledClock(clock)
    deps.config.feature_attention = deps.config.feature_observations = deps.config.feature_hitl = True
    app = build_app(deps)
    canonical_paths = canonical_artifact_paths(deps.connection_factory, home)
    before = benchmark.productive(deps.connection_factory)
    reads = []
    instrumentation = None
    try:
        with observe(deps.connection_factory, home.parent / "synthetic-artifacts", canonical_paths) as instrumentation:
            async with AsyncClient(transport=ASGITransport(app, client=("127.0.0.1", 65123)), base_url="http://j04-own.invalid") as client:
                async def get(path, params):
                    response = await client.get(path, params=params)
                    read = {"path": path, "http_status": response.status_code, "bytes": len(response.content),
                        "response_sha256": hashlib.sha256(response.content).hexdigest()}
                    reads.append(read)
                    assert response.status_code == 200, (path, response.status_code)
                    assert MARKER.encode() not in response.content
                    body = response.json().get("data", response.json())
                    read.update(item_count=len(body.get("items", [])), total=body.get("total"), has_more=body.get("has_more"))
                    return body

                overview = await get("/api/v1/home/overview", {"workspace_id": "hst-perf"})
                assert overview, "Nonempty overview envelope required"
                board = await get("/api/v1/home/harness-board", {"workspace_id": "hst-perf", "presentation_version": 2, "limit": 3, "preview": 2})
                assert any(lane["items"] for lane in board["columns"].values())
                assert all(len(lane["items"]) <= 3 for lane in board["columns"].values())
                assert all(len(item.get("events_preview", [])) <= 2 for lane in board["columns"].values() for item in lane["items"] if item["kind"] == "harness")
                first = await get("/api/v1/home/results", {"workspace_id": "hst-perf", "limit": 3})
                assert len(first["items"]) == 3 and first["has_more"] and first["next_cursor"]
                assert first["total"] == 25 and first["total_is_exact"] is True
                second = await get("/api/v1/home/results", {"workspace_id": "hst-perf", "limit": 3, "cursor": first["next_cursor"]})
                assert len(second["items"]) == 3
                assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])
                assert any(item.get("artifacts") for item in first["items"] + second["items"]), "Nonempty artifact metadata required"
                assert all(len(item.get("preview") or "") <= 401 for item in first["items"] + second["items"])
            assert not instrumentation["full_payload_materialized"], instrumentation
            assert not instrumentation["artifact_content_sql_reads"] and not instrumentation["artifact_file_reads"], instrumentation
        assert benchmark.productive(deps.connection_factory) == before
        return {"reads": reads, "instrumentation": instrumentation, "productive_rows_unchanged": True,
            "canonical_artifact_paths": canonical_paths}
    finally:
        try:
            deps.connection_factory.close()
        finally:
            # Diagnostic only: keep partial observations on any assertion/error,
            # without completing, weakening or replaying the original checks.
            save(home.parent / "partial-read-diagnostics.json", {"reads": reads,
                "instrumentation": instrumentation, "canonical_artifact_paths": canonical_paths, "latencies_collected": False})


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    assert sha(args.manifest) == args.manifest_sha256
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.root.resolve()
    assert json.loads((root / ".j04-owned.json").read_text()) == {"root": str(root), "kind": "j04-functional-synthetic-only"}
    ready = json.loads(Path(manifest["ready"]).read_text(encoding="utf-8"))
    benchmark = load("j04_original_benchmark_helpers", PERF / "benchmark.py")
    protocol = load("j04_original_persistent_guards", PERF / "persistent-worker.py")
    result = {"status": "INCOMPLETE", "layer": "SQL synthetic fixture + installed real ASGI/SQLite, lifespan off; no native authority proof", "latencies_collected": False}
    before = benchmark.payload(ready)
    home = root / "home"
    try:
        with protocol.guarded():
            assert benchmark.schema(home / "nexus.db") == manifest["schema_sha256"]
            from okto_nexus.bootstrap.dependencies import bootstrap

            preparation = bootstrap({}, ["--home", str(home), "--embedding-mode", "off"])
            try:
                # Use the installed factory so its actual registered trigger
                # functions remain intact; no invented writer UDF/authority.
                result["volume"] = augment(preparation.connection_factory, root, manifest["clock"])
            finally:
                preparation.connection_factory.close()
            result["augmented_database_sha256"] = sha(home / "nexus.db")
            result.update(asyncio.run(exercise(home, manifest["clock"], benchmark)))
            result["status"] = "PASS_FUNCTIONAL_HISTORY_SCOPE"
    finally:
        result["payload_drift"] = benchmark.payload(ready) != before
        benchmark.origin_guard()
        result["origins"] = {name: {"origin": value["origin"], "count": value["count"]} for name, value in before.items()}
        assert not result["payload_drift"]
        save(root / "result.json", result)


if __name__ == "__main__":
    main()
