"""TC2 - CLI ``admin export`` tests (spec c7c1f834, TS2 + TS3 + TS4).

Drives the real bootstrap in an isolated temp home through the shared tool
registry, then the ``admin export`` subcommand (and, for TS2, the REST handler
via TestClient) - proving valid NDJSON, correct recorte, CLI<->REST byte
identity, and that the CLI is UNGATED by feature_replay.
"""

from __future__ import annotations

import io
import json

import pytest

from okto_nexus.adapters.inbound.cli.admin import run_admin
from okto_nexus.testing import build_hub, pin_clock

pytestmark = pytest.mark.replay

_TRACE = "trace-cli-001"


def _ok(env):
    assert env["ok"] is True, env
    return env["data"]


def _direct(agent):
    return {"strategy": "direct", "agent_id": agent}


def _seed(hub):
    """A multi-stream, multi-trace scenario; returns (root, workspace_id)."""
    tools = hub.tools
    clock = pin_clock(hub.deps, 1_800_000_000.0)
    project = hub.home / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    wid = _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]
    for aid, role in (("alpha", "builder"), ("beta", "executor")):
        _ok(tools["agent_register"](agent_id=aid, role=role))

    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="m1",
            body="x",
            target=_direct("beta"),
        )
    )
    clock.advance(5)
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="traced",
            body="y",
            target=_direct("beta"),
            trace_id=_TRACE,
        )
    )
    clock.advance(5)
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="all",
            body="z",
            target={"strategy": "broadcast"},
        )
    )
    clock.advance(10)
    h = _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="job",
        )
    )["handoff_id"]
    clock.advance(10)
    _ok(tools["handoff_claim"](project_root=root, handoff_id=h, agent_id="beta"))
    clock.advance(30)
    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=h, agent_id="beta", result={"ok": True}
        )
    )
    clock.set(1_800_001_000.0)  # freeze -> reproducible generated_at
    return root, wid


def _cli(hub, root, *args):
    out = io.StringIO()
    rc = run_admin(
        ["export", "--project-root", root, *args],
        env={"OKTO_NEXUS_HOME": str(hub.home)},
        out=out,
        deps_factory=lambda env, extra: hub.deps,
    )
    assert rc == 0, f"CLI export exited {rc}"
    return out.getvalue()


def _split(text):
    lines = text.splitlines()
    return json.loads(lines[0]), [json.loads(x) for x in lines[1:]]


def _drop_generated_at(manifest):
    return {k: v for k, v in manifest.items() if k != "generated_at"}


# --------------------------------------------------------------------------- #
# TS3 - valid NDJSON, event_id ASC, filters echoed in the manifest
# --------------------------------------------------------------------------- #
def test_ts3_full_export_is_valid_ndjson_ascending() -> None:
    hub = build_hub()
    root, wid = _seed(hub)
    manifest, events = _split(_cli(hub, root))

    assert manifest["kind"] == "manifest"
    assert manifest["format_version"] == 1
    assert manifest["workspace_id"] == wid
    assert manifest["filters"] == {
        "stream": None,
        "trace_id": None,
        "since_event_id": 0,
        "until_event_id": None,
    }
    ids = [e["event_id"] for e in events]
    assert ids == sorted(ids) and len(ids) == len(set(ids))  # strictly ASC, unique
    assert manifest["event_count"] == len(events)
    assert manifest["event_id_min"] == ids[0]
    assert manifest["event_id_max"] == ids[-1]


def test_ts3_stream_filter_recorta_and_echoes() -> None:
    hub = build_hub()
    root, _ = _seed(hub)
    manifest, events = _split(_cli(hub, root, "--stream", "handoff"))
    assert manifest["filters"]["stream"] == "handoff"
    assert events and all(e["stream"] == "handoff" for e in events)
    assert manifest["event_count"] == len(events)


def test_ts3_since_is_exclusive_and_until_inclusive() -> None:
    hub = build_hub()
    root, _ = _seed(hub)
    _, all_events = _split(_cli(hub, root))
    ids = [e["event_id"] for e in all_events]
    pivot = ids[len(ids) // 2]

    _, after = _split(_cli(hub, root, "--since-event-id", str(pivot)))
    assert all(e["event_id"] > pivot for e in after)  # exclusive lower bound

    _, upto = _split(_cli(hub, root, "--until-event-id", str(pivot)))
    assert all(e["event_id"] <= pivot for e in upto)  # inclusive upper bound
    # the two half-open recortes partition the full log at the pivot
    assert pivot in [e["event_id"] for e in upto]
    assert pivot not in [e["event_id"] for e in after]


def test_ts3_trace_filter_positive_and_echoed() -> None:
    # feature_trace ON so the traced message actually stamps trace_id on its
    # event payload (the recorte is via json_extract($.trace_id)).
    hub = build_hub({"OKTO_NEXUS_FEATURE_TRACE": "true"})
    root, _ = _seed(hub)
    manifest, events = _split(_cli(hub, root, "--trace-id", _TRACE))
    assert manifest["filters"]["trace_id"] == _TRACE
    # exactly the one traced message survives the json_extract recorte
    assert len(events) == 1
    assert events[0]["type"] == "message.created"
    assert events[0]["payload"].get("trace_id") == _TRACE


def test_ts3_trace_filter_absent_yields_empty_recorte() -> None:
    hub = build_hub()
    root, _ = _seed(hub)
    manifest, events = _split(_cli(hub, root, "--trace-id", "no-such-trace"))
    assert events == []
    assert manifest["event_count"] == 0
    assert manifest["event_id_min"] is None and manifest["event_id_max"] is None


# --------------------------------------------------------------------------- #
# TS2 - CLI <-> REST byte identity for the same recorte
# --------------------------------------------------------------------------- #
def test_ts2_cli_and_rest_are_byte_identical_modulo_generated_at() -> None:
    hub = build_hub({"OKTO_NEXUS_FEATURE_REPLAY": "true"})
    root, wid = _seed(hub)

    cli_text = _cli(hub, root, "--stream", "handoff")

    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(hub.deps.repos.agents, hub.deps.clock)
    issued = ensure_operator_key(hub.deps, auth)
    assert issued is not None
    _, operator_key = issued
    client = TestClient(build_app(hub.deps))
    client.headers.update({"x-api-key": operator_key})

    resp = client.get(
        f"/api/v1/workspaces/{wid}/events/export", params={"stream": "handoff"}
    )
    assert resp.status_code == 200, resp.text
    rest_text = resp.text

    cli_manifest, cli_events = _split(cli_text)
    rest_manifest, rest_events = _split(rest_text)

    # event lines: byte-identical (the single canonical serializer, BR3)
    assert cli_text.splitlines()[1:] == rest_text.splitlines()[1:]
    assert cli_events == rest_events
    # manifest: identical except (at most) generated_at
    assert _drop_generated_at(cli_manifest) == _drop_generated_at(rest_manifest)


# --------------------------------------------------------------------------- #
# TS4 - CLI export works with feature_replay OFF (ungated, D3/BR1)
# --------------------------------------------------------------------------- #
def test_ts4_cli_export_runs_with_feature_replay_off() -> None:
    # No OKTO_NEXUS_FEATURE_REPLAY in the env -> flag OFF by default.
    hub = build_hub()
    assert hub.deps.config.feature_replay is False
    root, wid = _seed(hub)

    text = _cli(hub, root)  # exits 0 (asserted inside _cli)
    manifest, events = _split(text)
    assert manifest["workspace_id"] == wid
    assert events, "CLI must still produce the full NDJSON with the flag OFF"
