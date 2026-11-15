"""Read-only loopback fixture for real-browser HOME-R1 qualification.

Run with the development Python, not as a production Nexus entry point. It
serves the built dashboard and real GET handlers over synthetic disposable data;
mutations are rejected and the application runtime lifespan is never started.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from fastapi.responses import JSONResponse
import uvicorn

from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app


def seed(deps):
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        for workspace, name in (("home-alpha", "Orion workspace"), ("home-beta", "Lyra workspace")):
            deps.repos.workspaces.upsert(uow, workspace_id=workspace)
            c.execute("UPDATE workspaces SET display_name=? WHERE workspace_id=?", (name, workspace))
        for agent in ("A", "B", "C", "global", *(f"worker-{index}" for index in range(8))):
            deps.repos.agents.upsert(uow, agent_id=agent, role="worker")
        for sid, agent, workspace in (("A-orion", "A", "home-alpha"),
                                      ("A-lyra", "A", "home-beta"),
                                      ("B-orion", "B", "home-alpha"),
                                      ("C-orion", "C", "home-alpha")):
            deps.repos.sessions.create(uow, session_id=sid, agent_id=agent,
                                       workspace_id=workspace, status="active")
        records = [
            ("home-alpha", "A", "B", "OPEN", "Review the integration"),
            ("home-alpha", "B", "C", "CLAIMED", "Validate the response"),
            ("home-alpha", "C", "A", "VERIFYING", "Verify the delivery"),
            ("home-alpha", "C", "A", "COMPLETED", "Document the result"),
            ("home-beta", "A", "C", "OPEN", "Lyra: independent request"),
        ]
        records.extend(("home-alpha", "A", f"worker-{index % 8}", "OPEN", f"Review batch item {index+1:02d}")
                       for index in range(12))
        for index, (workspace, sender, recipient, state, title) in enumerate(records):
            task, handoff = f"browser-task-{index}", f"browser-handoff-{index}"
            stamp = (datetime.fromisoformat(now.replace('Z', '+00:00')) - timedelta(seconds=index)).isoformat()
            c.execute("INSERT INTO tasks(task_id,workspace_id,title,status,created_by,created_at) "
                      "VALUES(?,?,?,'OPEN',?,?)", (task, workspace, title, sender, stamp))
            c.execute("INSERT INTO handoffs(handoff_id,workspace_id,task_id,from_agent_id,target,visibility,status,claimed_by,created_at,updated_at) "
                      "VALUES(?,?,?,?,?,'eligible',?,?,?,?)",
                      (handoff, workspace, task, sender, json.dumps({"strategy": "direct", "agent_id": recipient}),
                       state, recipient if state != "OPEN" else None, stamp, stamp))
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,subject,body,created_at) "
                  "VALUES('browser-message','home-alpha','B','Coordination update','Synthetic informational message',?)", (now,))
        c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) "
                  "VALUES('browser-delivery','browser-message','C','unread',?)", (now,))


async def serve(app, *, port, stop_file, ready_file, fixture_home):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="warning")
    server = uvicorn.Server(config)
    sock = config.bind_socket()
    actual_port = sock.getsockname()[1]

    async def stop_when_requested():
        while not server.should_exit:
            if stop_file.exists():
                server.should_exit = True
                return
            await asyncio.sleep(.2)

    watcher = asyncio.create_task(stop_when_requested())
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    files = ["tests/home_evolution/browser_fixture.py", "tests/home_evolution/browser_checks.js",
             "src/okto_nexus/application/home.py", "src/okto_nexus/domain/home.py",
             "src/okto_nexus/adapters/outbound/sqlite/home.py",
             "src/okto_nexus/adapters/inbound/http/home.py",
             "src/okto_nexus/adapters/inbound/http/routes.py",
             "src/okto_nexus/adapters/inbound/http/static/index.html"]
    ready_file.write_text(json.dumps(dict(url=f"http://127.0.0.1:{actual_port}",
        fixture_home=str(fixture_home), synthetic=True, mutations=False, runtime_started=False,
        source_pins={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}), indent=2), encoding="utf-8")
    print(f"HOME-R1 synthetic read-only fixture: http://127.0.0.1:{actual_port}", flush=True)
    try:
        await server.serve(sockets=[sock])
    finally:
        watcher.cancel()
        sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    # Windows can retain handles from source readers until process teardown.
    # The controlling test removes this verified synthetic path after exit;
    # never recursively remove a live home during fixture shutdown.
    temporary = Path(tempfile.mkdtemp(prefix="nexus-home-r1-browser-"))
    deps = bootstrap({}, ["--home", str(temporary)])
    try:
        seed(deps)
        app = build_app(deps)

        @app.middleware("http")
        async def read_only(request, call_next):
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                return JSONResponse({"fixture": "Synthetic read-only preview; mutations disabled."}, status_code=405)
            return await call_next(request)

        asyncio.run(serve(app, port=args.port, stop_file=args.stop_file, ready_file=args.ready_file,
                          fixture_home=temporary))
    finally:
        deps.connection_factory.close()


if __name__ == "__main__":
    main()
