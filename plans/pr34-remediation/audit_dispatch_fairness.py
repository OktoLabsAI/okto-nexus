"""Disposable production HTTP composition; observe lane selection, never native models."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from test_pr34_remediation import runtime, open_rest, send_message  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix="okto-fairness-audit-") as directory:
        fixture = runtime.__wrapped__(Path(directory), SimpleNamespace(param=True))
        current = next(fixture)
        try:
            deps, client, root, _, operator, _ = current
            assert open_rest(current).status_code == 200
            with deps.connection_factory.unit_of_work() as uow:
                deps.repos.agents.upsert(uow, agent_id="healthy", role="reviewer")
            headers = {"x-api-key": operator}
            response = client.post("/api/v1/harness/endpoints", headers=headers, json={
                "endpoint_id": "healthy-endpoint", "agent_id": "healthy", "adapter_id": "pi",
                "project_root": root, "profile_id": "profile-pi", "enabled": True,
                "response_policy": "conversation"})
            assert response.status_code == 200, response.text
            response = client.post("/api/v1/harness/sessions", headers=headers, json={
                "agent_id": "healthy", "kind": "pi", "endpoint_id": "healthy-endpoint", "project_root": root})
            assert response.status_code == 200, response.text
            deps.runtime_dispatcher.quiesce()
            for recipient in ("worker", "worker", "healthy"):
                send_message(current, target={"strategy": "direct", "agent_id": recipient})
            with deps.connection_factory.unit_of_work(write=False) as uow:
                rows = deps.runtime_dispatcher.repo.pending(uow, limit=2)
                count = uow.connection.execute("SELECT count(*) FROM delivery_outbox WHERE status='PENDING'").fetchone()[0]
            selected = [row["recipient_agent_id"] for row in rows]
            result = {"source_sha": "43388c8", "requirement": "T-DISP-09",
                "command": "rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/audit_dispatch_fairness.py <evidence.json>",
                "composition": "authenticated real HTTP; approved synthetic Pi peers; dispatcher quiesced before enqueue",
                "pending": count, "worker_capacity": 2, "selected_recipients": selected,
                "unique_selected_lanes": len({row["endpoint_id"] for row in rows}),
                "expected": "two distinct eligible lanes, including healthy",
                "status": "PASS" if len(set(selected)) == 2 and "healthy" in selected else "FAIL",
                "limitation": "selection-stage reproduction; not a wall-clock scheduler-pressure benchmark"}
            Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2))
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass


if __name__ == "__main__":
    main()
