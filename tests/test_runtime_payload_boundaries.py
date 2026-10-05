"""Native launch/control payloads never override approved execution authority."""
import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool

runtime = runtime_fixture


def test_unapproved_launch_options_are_rejected_before_spawn_on_both_surfaces(runtime):
    deps, client, root, peers, operator, _ = runtime
    options = {"cwd": "unapproved", "sandbox": "danger-full-access", "provider": "unapproved",
        "env": {"FIXTURE_ONLY": "unapproved"}, "argv": ["unapproved"]}
    for key, value in options.items():
        arguments = {"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex",
            "project_root": root, "backend": {key: value}}
        mcp = tool(client, operator, "harness_open", arguments)
        rest = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=arguments)
        assert not mcp["ok"] and mcp["error"]["code"] == "VALIDATION_ERROR", (key, mcp)
        assert rest.status_code == 422, (key, rest.text)
    assert peers == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM harness_sessions").fetchone()


@pytest.mark.parametrize("verb", ["send", "steer", "interrupt"])
def test_control_payload_cannot_replace_identity_correlation_or_native_profile(runtime, verb):
    deps, client, root, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    fields = {"actor_agent_id": "operator", "from_agent_id": "operator", "grant_id": "forged",
        "root_operation_id": "forged", "cwd": root + "-other", "sandbox": "danger-full-access",
        "provider": "unapproved", "env": {"FIXTURE_ONLY": "unapproved"}, "argv": ["unapproved"]}
    for key, value in fields.items():
        args = {"payload": {"text": "never sent", key: value}}
        mcp = tool(client, operator, "harness_" + verb, {"session_id": sid, **args})
        rest = client.post(f"/api/v1/harness/sessions/{sid}/{verb}", headers={"x-api-key": operator}, json=args)
        assert not mcp["ok"] and mcp["error"]["code"] == "VALIDATION_ERROR", (key, mcp)
        assert rest.status_code == 422, (key, rest.text)
    assert len(peers) == 1 and not peers[0].sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands").fetchone()
