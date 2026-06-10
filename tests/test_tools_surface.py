"""Behavioural contract of the M3 safe-by-default MCP surface.

Every test here calls tools through the REAL FastMCP server (``create_server``
over a real migrated temp store) via ``server.call_tool`` - i.e. through the
exact validation path agents hit - and asserts on observable effects:

* the S3 migration shims answer ``ok:false code=MIGRATED`` with a prescriptive
  message naming the replacement tools, and tolerate any legacy argument shape;
* ``nexus_info`` reports ``package_version`` / ``schema_version`` (the highest
  applied migration, cross-checked against the shipped migration FILES) /
  ``surface_revision``;
* ``event_wait`` with ``timeout_seconds`` omitted (or null) is an immediate
  snapshot - it must NOT park the turn for the 30s server ceiling - while an
  explicit ``timeout_seconds > 0`` still opts in to the blocking long-poll;
* ``handoff_create`` accepts a RAW dict ``payload`` end-to-end (create ->
  list_available -> claim echo the serialised JSON TEXT);
* wrong-typed ``target`` / ``limit`` / ``timeout_seconds`` come back as the
  canonical ``VALIDATION_ERROR`` envelope, never as an SDK validation error.

The SCHEMA-level counterparts (descriptions, defaults, published shims) live in
``test_tool_schemas.py``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import pytest

from okto_nexus.adapters.inbound.mcp.server import (
    SURFACE_REVISION,
    bootstrap,
    create_server,
)

pytest.importorskip("mcp", reason="MCP SDK required to call tools via FastMCP")


@pytest.fixture
def surface(tmp_path):
    """A live FastMCP server over a real migrated store + a real project dir."""
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    server = create_server(deps)
    project = tmp_path / "project"
    project.mkdir()
    return server, str(project)


def _call(server, name: str, arguments: dict | None = None) -> dict:
    """Call a tool through FastMCP (schema validation included); return the envelope."""
    result = asyncio.run(server.call_tool(name, arguments or {}))
    if isinstance(result, tuple):  # (unstructured, structured) when output schema exists
        return result[1]
    block = result[0]
    return json.loads(block.text)


# --------------------------------------------------------------------------- #
# S3 migration shims
# --------------------------------------------------------------------------- #
def test_message_get_shim_returns_prescriptive_migrated(surface):
    server, _ = surface
    env = _call(server, "message_get")
    assert env["ok"] is False
    error = env["error"]
    assert error["code"] == "MIGRATED"
    for replacement in ("inbox_pull", "inbox_peek", "inbox_history", "inbox_ack"):
        assert replacement in error["message"], (
            f"message_get MIGRATED message must point at {replacement}"
        )
    assert error["details"]["removed_in"] == "S3"
    assert "inbox_pull" in error["details"]["replacements"]


def test_message_list_and_wait_shims_point_at_exact_replacements(surface):
    server, _ = surface

    env_list = _call(server, "message_list")
    assert env_list["ok"] is False
    assert env_list["error"]["code"] == "MIGRATED"
    for replacement in ("inbox_peek", "inbox_history", "event_get"):
        assert replacement in env_list["error"]["message"]

    env_wait = _call(server, "message_wait")
    assert env_wait["ok"] is False
    assert env_wait["error"]["code"] == "MIGRATED"
    for replacement in ("inbox_count", "inbox_pull", "event_wait"):
        assert replacement in env_wait["error"]["message"]
    # The replacement guidance includes the equivalent parameters.
    assert "timeout_seconds" in env_wait["error"]["message"]


def test_shims_tolerate_any_legacy_argument_shape(surface):
    """Old clients pass pre-S3 params; they must land on the shim, not on a
    second (SDK) error grammar."""
    server, project = surface

    legacy_calls = [
        ("message_get", {"project_root": project, "message_id": "msg_123"}),
        ("message_list", {"project_root": project, "channel_id": "ch_1", "limit": 10}),
        ("message_wait", {"project_root": project, "timeout_seconds": 5, "cursor": 7}),
    ]
    for name, legacy_args in legacy_calls:
        env = _call(server, name, legacy_args)
        assert env["ok"] is False, f"{name} must answer with an envelope"
        assert env["error"]["code"] == "MIGRATED", (
            f"{name} with legacy args must still answer MIGRATED, got: {env}"
        )


# --------------------------------------------------------------------------- #
# nexus_info
# --------------------------------------------------------------------------- #
def test_nexus_info_reports_versions(surface):
    server, _ = surface
    env = _call(server, "nexus_info")
    assert env["ok"] is True
    data = env["data"]
    assert set(data) == {"package_version", "schema_version", "surface_revision"}

    assert isinstance(data["package_version"], str) and data["package_version"]

    # schema_version is the ledger MAX(version); cross-check it against the
    # shipped migration FILES (independent source of truth).
    import okto_nexus

    migrations_dir = Path(okto_nexus.__file__).resolve().parent / "migrations"
    versions = [
        int(m.group(1))
        for p in migrations_dir.glob("*.sql")
        if (m := re.match(r"^(\d+)_", p.name))
    ]
    assert versions, "expected packaged migration files"
    assert data["schema_version"] == max(versions)

    assert isinstance(data["surface_revision"], int)
    assert data["surface_revision"] == SURFACE_REVISION
    assert data["surface_revision"] >= 2  # started at 2 with the M3 surface


# --------------------------------------------------------------------------- #
# event_wait: snapshot by default, blocking opt-in
# --------------------------------------------------------------------------- #
def test_event_wait_omitted_timeout_is_immediate_snapshot(surface):
    server, project = surface
    args = {"project_root": project, "agent_id": "watcher", "stream": "workspace"}

    start = time.monotonic()
    env = _call(server, "event_wait", args)
    elapsed = time.monotonic() - start

    assert env["ok"] is True
    assert env["data"]["events"] == []
    assert env["data"]["timed_out"] is True
    # The server ceiling is 30s; a snapshot returns in milliseconds. The bound
    # is generous only to absorb CI jitter.
    assert elapsed < 5.0, f"omitted timeout must not block (took {elapsed:.1f}s)"

    # An explicit null is the same snapshot, not "use the server ceiling".
    start = time.monotonic()
    env_null = _call(server, "event_wait", {**args, "timeout_seconds": None})
    elapsed_null = time.monotonic() - start
    assert env_null["ok"] is True and env_null["data"]["timed_out"] is True
    assert elapsed_null < 5.0


def test_event_wait_positive_timeout_still_blocks(surface):
    """Long-poll remains available as an explicit opt-in."""
    server, project = surface
    start = time.monotonic()
    env = _call(
        server,
        "event_wait",
        {
            "project_root": project,
            "agent_id": "watcher",
            "stream": "workspace",
            "timeout_seconds": 1,
        },
    )
    elapsed = time.monotonic() - start
    assert env["ok"] is True
    assert env["data"]["timed_out"] is True
    assert elapsed >= 0.9, f"timeout_seconds=1 must long-poll (took {elapsed:.2f}s)"


# --------------------------------------------------------------------------- #
# handoff_create: raw dict payload end-to-end
# --------------------------------------------------------------------------- #
def test_handoff_create_accepts_raw_dict_payload_end_to_end(surface):
    server, project = surface
    assert _call(server, "workspace_resolve", {"project_root": project})["ok"] is True
    assert _call(server, "agent_register", {"agent_id": "producer"})["ok"] is True
    assert _call(server, "agent_register", {"agent_id": "worker"})["ok"] is True

    payload = {"task": "ocr", "pages": [1, 2], "lang": "pt-BR"}
    created = _call(
        server,
        "handoff_create",
        {
            "project_root": project,
            "from_agent_id": "producer",
            "target": {"strategy": "broadcast"},
            "visibility": "public",
            "payload": payload,  # raw dict - NO JSON-escaping by the client
        },
    )
    assert created["ok"] is True, f"dict payload must validate: {created}"
    handoff_id = created["data"]["handoff_id"]

    available = _call(
        server,
        "handoff_list_available",
        {"project_root": project, "agent_id": "worker"},
    )
    assert available["ok"] is True
    entries = [
        h for h in available["data"]["handoffs"] if h["handoff_id"] == handoff_id
    ]
    assert entries, "the broadcast handoff must be claimable by the worker"
    # Stored/echoed as opaque JSON TEXT that round-trips to the original dict.
    assert json.loads(entries[0]["payload"]) == payload

    claimed = _call(
        server,
        "handoff_claim",
        {"project_root": project, "handoff_id": handoff_id, "agent_id": "worker"},
    )
    assert claimed["ok"] is True
    assert json.loads(claimed["data"]["payload"]) == payload


# --------------------------------------------------------------------------- #
# Wrong-typed inputs -> canonical envelope (single error grammar)
# --------------------------------------------------------------------------- #
def test_wrong_typed_target_returns_canonical_envelope(surface):
    server, project = surface

    bad_message = _call(
        server,
        "message_create",
        {
            "project_root": project,
            "from_agent_id": "producer",
            "subject": "s",
            "body": "b",
            "target": "worker",  # bare string, not a routing object
        },
    )
    assert bad_message["ok"] is False
    assert bad_message["error"]["code"] == "VALIDATION_ERROR"

    bad_handoff = _call(
        server,
        "handoff_create",
        {
            "project_root": project,
            "from_agent_id": "producer",
            "target": 42,  # a number can never be a routing object
            "visibility": "public",
        },
    )
    assert bad_handoff["ok"] is False
    assert bad_handoff["error"]["code"] == "VALIDATION_ERROR"
    assert "JSON object" in bad_handoff["error"]["message"]


def test_wrong_typed_limit_and_timeout_return_canonical_envelope(surface):
    server, project = surface
    base = {"project_root": project, "agent_id": "watcher", "stream": "workspace"}

    bad_limit = _call(server, "event_get", {**base, "limit": "ten"})
    assert bad_limit["ok"] is False
    assert bad_limit["error"]["code"] == "VALIDATION_ERROR"

    bad_timeout = _call(server, "event_wait", {**base, "timeout_seconds": "soon"})
    assert bad_timeout["ok"] is False
    assert bad_timeout["error"]["code"] == "VALIDATION_ERROR"
