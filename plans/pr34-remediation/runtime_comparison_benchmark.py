"""Same-host original/current HTTP turn latency, preserving each revision's controls."""
import argparse
import ast
from contextlib import closing
import hashlib
import inspect
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import socket
import sqlite3
import sys
import tempfile
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("peer_source", type=Path)
    parser.add_argument("sha")
    parser.add_argument("output", type=Path)
    parser.add_argument("--samples", type=int, default=40)
    args = parser.parse_args()
    assert 5 <= args.samples <= 100
    sys.path.insert(0, str(args.repo.resolve() / "src"))
    import httpx
    import uvicorn
    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from okto_nexus.application.auth import AgentKeyAuthService
    logging.disable(logging.INFO)
    assert Path(inspect.getfile(bootstrap)).resolve().is_relative_to(args.repo.resolve())

    source = ast.parse(args.peer_source.read_text(encoding="utf-8"))
    peer_text = next(ast.literal_eval(n.value) for n in source.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_FAKE_SERVER_SOURCE" for t in n.targets))
    measurements = {"fsync": [], "authentication": [], "runtime_policy": []}
    restorations = []

    def instrument(owner, name, bucket):
        original = getattr(owner, name)
        def measured(*positional, **keywords):
            start = time.perf_counter_ns()
            try:
                return original(*positional, **keywords)
            finally:
                measurements[bucket].append((time.perf_counter_ns() - start) / 1e6)
        setattr(owner, name, measured)
        restorations.append((owner, name, original))

    instrument(os, "fsync", "fsync")
    instrument(AgentKeyAuthService, "resolve", "authentication")
    modern = (args.repo / "src/okto_nexus/application/runtime_access.py").exists()
    if modern:
        from okto_nexus.application.runtime_access import RuntimeAccessService
        instrument(RuntimeAccessService, "authorize", "runtime_policy")
    result = {"status": "RUNNING", "sha": args.sha, "python": sys.version,
        "platform": platform.platform(), "cpu_count": os.cpu_count(), "modern": modern,
        "dependencies": {n: importlib.metadata.version(n) for n in ("httpx", "uvicorn", "fastapi", "mcp")},
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "peer_sha256": hashlib.sha256(peer_text.encode()).hexdigest(), "warmup": 5, "samples": [],
        "limitations": ["Synthetic local Codex peer; no provider latency or native qualification",
            "Original has no new authorization/journal guarantees; their absence is measured, never emulated",
            "Terminal timing observes persisted SQLite events at1ms intervals; not native status polling",
            "Python os.fsync timing includes journal; SQLite internal C fsync is inside end-to-end latency only",
            "Nested/concurrent timing categories are observations, not additive causal overhead estimates"]}
    try:
        with tempfile.TemporaryDirectory(prefix="okto-benchmark-") as directory:
            root = Path(directory)
            os.environ["HOME"] = str(root)
            os.environ["USERPROFILE"] = str(root)
            project = root / "project"
            project.mkdir()
            home = root / "home"
            deps = bootstrap({}, ["--home", str(home)])
            deps.config.feature_harness_integrations = True
            deps.config.embedding_mode = "off"
            env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
            env.update(HOME=str(root), USERPROFILE=str(root), PYTHONIOENCODING="utf-8")
            peers = []
            def factory(**kwargs):
                peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", peer_text], cwd=str(project), env=env)
                peers.append(peer)
                return peer
            deps.harness_connector_factories = {"codex": factory}
            auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
            _, key = ensure_operator_key(deps, auth)
            with deps.connection_factory.unit_of_work() as uow:
                deps.repos.agents.upsert(uow, agent_id="benchmark-worker", role="reviewer")
            ready = threading.Event()
            class Server(uvicorn.Server):
                async def startup(self, sockets=None):
                    await super().startup(sockets)
                    ready.set()
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            options = {"runtime_owner_api_url": url} if "runtime_owner_api_url" in inspect.signature(build_app).parameters else {}
            app = build_app(deps, **options)
            # Require credentials on both revisions, using the production
            # setting serve uses for non-loopback listeners; keep socket local.
            app.state.local_open = False
            result["local_open"] = False
            server = Server(uvicorn.Config(app, log_level="error"))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
            thread.start()
            try:
                assert ready.wait(20)
                with httpx.Client(base_url=url, headers={"x-api-key": key}, timeout=20) as client:
                    if modern:
                        for path, body in [("profiles", {"profile_id": "bench", "adapter_id": "codex", "enabled": True}),
                            ("endpoints", {"endpoint_id": "bench", "profile_id": "bench", "adapter_id": "codex",
                                "agent_id": "benchmark-worker", "enabled": True, "project_root": str(project)})]:
                            response = client.post("/api/v1/harness/" + path, json=body)
                            assert response.status_code == 200, response.text
                    body = {"agent_id": "benchmark-worker", "kind": "codex", "project_root": str(project)}
                    if modern:
                        body["endpoint_id"] = "bench"
                    opened = client.post("/api/v1/harness/sessions", json=body)
                    assert opened.status_code == 200, opened.text
                    sid = opened.json()["data"]["session_id"]
                    denied = client.post(f"/api/v1/harness/sessions/{sid}/send",
                        headers={"x-api-key": "invalid-benchmark-key"}, json={"payload": {"text": "must-not-run"}})
                    assert denied.status_code in {401, 403}, denied.text
                    result["invalid_credential_status"] = denied.status_code
                    cursor = 0
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        result["sqlite_settings"] = {name: uow.connection.execute("PRAGMA " + name).fetchone()[0]
                            for name in ("synchronous", "journal_mode")}
                    for index in range(args.samples + 5):
                        offsets = {k: len(v) for k, v in measurements.items()}
                        start = time.perf_counter_ns()
                        response = client.post(f"/api/v1/harness/sessions/{sid}/send",
                            json={"payload": {"text": f"benchmark-{index:03d}:" + "x" * 1024}})
                        admitted = time.perf_counter_ns()
                        assert response.status_code == 200, response.text
                        deadline = time.monotonic() + 10
                        while True:
                            with closing(sqlite3.connect(home / "nexus.db")) as connection:
                                events = connection.execute("SELECT sequence,kind,payload FROM harness_events WHERE session_id=? AND sequence>? ORDER BY sequence", (sid, cursor)).fetchall()
                            if any(e[1] == "turn_completed" for e in events):
                                break
                            assert time.monotonic() < deadline, "No persisted terminal"
                            time.sleep(.001)
                        elapsed = (time.perf_counter_ns() - start) / 1e6
                        assert any(f"benchmark-{index:03d}:" in e[2] for e in events)
                        cursor = max(e[0] for e in events)
                        if modern:
                            op = response.json()["data"]["operation_id"]
                            with closing(sqlite3.connect(home / "nexus.db")) as connection:
                                assert connection.execute("SELECT count(*) FROM runtime_results WHERE command_operation_id=?", (op,)).fetchone()[0] == 1
                        sample = {"index": index, "admission_ms": (admitted-start)/1e6, "persisted_terminal_ms": elapsed,
                            "components": {k: {"count": len(v[offsets[k]:]), "total_ms": sum(v[offsets[k]:])}
                                for k, v in measurements.items()}}
                        if index >= 5:
                            result["samples"].append(sample)
                    assert all(s["components"]["authentication"]["count"] > 0 for s in result["samples"])
                    if modern:
                        assert all(s["components"]["fsync"]["count"] > 0 and s["components"]["runtime_policy"]["count"] > 0 for s in result["samples"])
            finally:
                supervisor = getattr(deps, "harness_supervisor", None)
                if supervisor:
                    for session in supervisor.list_live():
                        supervisor.close(session.session_id)
                server.should_exit = True
                thread.join(20)
                sock.close()
                assert not thread.is_alive()
                for peer in peers:
                    peer.close()
                    assert peer._transport._proc.poll() is not None
                result["owned_peers_stopped"] = len(peers)
        result["status"] = "PASS"
    except BaseException as exc:
        result["status"] = "FAIL"
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)[:1500]}
        raise
    finally:
        for owner, name, original in reversed(restorations):
            setattr(owner, name, original)
        args.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "samples": len(result["samples"])}))


if __name__ == "__main__":
    main()
