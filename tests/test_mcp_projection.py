"""MCP projection helper (Frente 2): profile resolution, per-profile field
disposition, dedup, follow_up, telemetry and the byte ceiling.

Operates on the EXACT dict shapes the core produces (domain.events.event_to_dict
and application.inbox.InboxService._item), so the projection contract is pinned
to the real surfaces.

Scenario coverage (spec 6cb93549):
* S1/AC1 - omitted profile -> default
* S2/AC2 - invalid profile -> VALIDATION_ERROR + supported list
* S3/AC3 - default safe-trim (dead/dup removed, contextuals kept)
* S4/AC4 - summary drops contextuals + omits body/payload, message_id kept
* S5/AC5 - full = raw
* S6/AC6 - follow_up shape + per-tool target_ref
* S7/AC7 - telemetry payload_bytes/omitted_count/truncated
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from okto_nexus.adapters.inbound.mcp.projection import (
    MAX_ITEM_BYTES,
    PROFILES,
    parse_profile,
    project_event,
    project_inbox_item,
    project_page,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

_SRC = Path(__file__).resolve().parents[1] / "src" / "okto_nexus"
_HELPER_MODULE = "adapters.inbound.mcp.projection"


def raw_event(**over):
    base = {
        "event_id": 42,
        "workspace_id": "ws1",
        "stream": "handoff",
        "type": "handoff.created",
        "payload": {"handoff_id": "h1", "task_id": None, "note": "hello"},
        "actor_agent_id": "orch",
        "task_id": None,
        "handoff_id": "h1",
        "created_at": "2026-06-19T12:00:00.000000Z",
    }
    base.update(over)
    return base


def raw_inbox(**over):
    base = {
        "delivery_id": "d1",
        "message_id": "m1",
        "status": "delivered",
        "delivered_at": "2026-06-19T12:00:00.000000Z",
        "lease_expires_at": "2026-06-19T12:05:00.000000Z",
        "read_at": None,
        "from_agent_id": "a",
        "workspace_id": "ws1",
        "channel_id": None,
        "subject": "hi",
        "target": {"strategy": "direct", "agent_id": "b"},
        "artifacts": [],
        "created_at": "2026-06-19T12:00:00.000000Z",
        "body": "hello world",
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# S1 / S2 - profile resolution
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [None, "", "  "])
def test_parse_profile_omitted_is_default(value):
    assert parse_profile(value) == "default"


@pytest.mark.parametrize("value", ["default", "summary", "full", "FULL", " Summary "])
def test_parse_profile_valid(value):
    assert parse_profile(value) in PROFILES


def test_parse_profile_invalid_raises_validation_error():
    with pytest.raises(OktoNexusError) as exc:
        parse_profile("foo")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR
    assert exc.value.details["supported"] == list(PROFILES)


# --------------------------------------------------------------------------- #
# S3 - default safe-trim (event + inbox)
# --------------------------------------------------------------------------- #
def test_event_default_safe_trim():
    out, omitted, truncated = project_event(raw_event(), "default")
    assert "task_id" not in out  # always-null dead weight removed
    assert out["handoff_id"] == "h1"  # non-null promoted scalar kept
    assert out["workspace_id"] == "ws1"  # contextual kept in default
    # payload deduped: the promoted scalars are gone, the rest remains
    assert out["payload"] == {"note": "hello"}
    assert omitted == 1 and truncated is False  # only task_id dropped


def test_inbox_default_keeps_contextuals_drops_empty_artifacts():
    out, omitted, truncated = project_inbox_item(raw_inbox(), "default")
    for k in (
        "target",
        "delivery_id",
        "workspace_id",
        "channel_id",
        "lease_expires_at",
        "read_at",
        "delivered_at",
        "body",
    ):
        assert k in out  # contextuals + body kept in default
    assert "artifacts" not in out  # empty [] dropped
    assert out["message_id"] == "m1"
    assert omitted == 1 and truncated is False


def test_inbox_default_keeps_non_empty_artifacts():
    out, _, _ = project_inbox_item(raw_inbox(artifacts=[{"name": "x"}]), "default")
    assert out["artifacts"] == [{"name": "x"}]


# --------------------------------------------------------------------------- #
# S4 - summary aggressive (message_id always present)
# --------------------------------------------------------------------------- #
def test_event_summary_drops_contextuals_and_payload():
    out, omitted, _ = project_event(raw_event(), "summary")
    for k in ("task_id", "handoff_id", "workspace_id", "payload"):
        assert k not in out
    assert out["follow_up"]["target_ref"] == "event_get"
    assert set(("event_id", "type", "actor_agent_id", "created_at", "stream")) <= set(
        out
    )
    assert omitted == 4  # task_id, handoff_id, workspace_id, payload


def test_inbox_summary_drops_contextuals_keeps_message_id():
    out, omitted, _ = project_inbox_item(raw_inbox(), "summary")
    for k in (
        "target",
        "delivery_id",
        "workspace_id",
        "channel_id",
        "lease_expires_at",
        "read_at",
        "delivered_at",
        "body",
    ):
        assert k not in out
    assert out["message_id"] == "m1"  # LOAD-BEARING, always present
    assert out["follow_up"]["target_ref"] == "inbox_peek"
    assert omitted == 9


def test_inbox_summary_peek_keeps_preview_no_follow_up():
    # peek item: body_preview/body_bytes instead of body; nothing heavy omitted.
    item = raw_inbox()
    del item["body"]
    item["body_preview"] = "hello"
    item["body_bytes"] = 11
    out, _, _ = project_inbox_item(item, "summary")
    assert out["body_preview"] == "hello"
    assert "follow_up" not in out  # no full body was omitted


# --------------------------------------------------------------------------- #
# S5 - full = raw
# --------------------------------------------------------------------------- #
def test_full_is_raw():
    ev = raw_event()
    out, omitted, truncated = project_event(ev, "full")
    assert out == ev and omitted == 0 and truncated is False
    ib = raw_inbox()
    out2, omitted2, _ = project_inbox_item(ib, "full")
    assert out2 == ib and omitted2 == 0


# --------------------------------------------------------------------------- #
# S6 - follow_up shape
# --------------------------------------------------------------------------- #
def test_follow_up_shape():
    out, _, _ = project_inbox_item(raw_inbox(), "summary")
    assert out["follow_up"] == {
        "rel": "read_full",
        "target_ref": "inbox_peek",
        "hint": "profile=full",
    }


# --------------------------------------------------------------------------- #
# truncation - oversized event payload omitted + follow_up + truncated
# --------------------------------------------------------------------------- #
def test_event_default_truncates_oversized_payload():
    big = {"note": "x" * (MAX_ITEM_BYTES + 100)}
    out, _, truncated = project_event(raw_event(payload=big), "default")
    assert truncated is True
    assert "payload" not in out
    assert out["follow_up"]["target_ref"] == "event_get"


# --------------------------------------------------------------------------- #
# S7 - telemetry via project_page
# --------------------------------------------------------------------------- #
def test_project_page_telemetry():
    page = project_page(
        [raw_inbox(), raw_inbox(message_id="m2")], "summary", kind="inbox"
    )
    assert page["truncated"] is False
    assert page["omitted_count"] == 18  # 9 per item, 2 items
    # payload_bytes is the deterministic compact-JSON size of the projected items
    expected = len(
        json.dumps(
            page["items"], ensure_ascii=False, separators=(",", ":"), default=str
        ).encode("utf-8")
    )
    assert page["payload_bytes"] == expected
    # message_id survives on every item (load-bearing)
    assert all("message_id" in it for it in page["items"])


def test_project_page_event_full_vs_summary_reduction():
    items = [raw_event(event_id=i) for i in range(5)]
    full = project_page(items, "full", kind="event")
    summary = project_page(items, "summary", kind="event")
    # summary must be materially smaller than full (the whole point).
    assert summary["payload_bytes"] < full["payload_bytes"]


# --------------------------------------------------------------------------- #
# S9 / AC9 - dedicated import-boundary guard (the existing test_import_boundary
# only bars sqlite3/mcp ROOTS, so the helper - root okto_nexus - would slip
# through; this guard catches a domain/application import of it specifically).
# --------------------------------------------------------------------------- #
def _imports_helper(py: Path) -> bool:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and _HELPER_MODULE in node.module
        ):
            return True
        if isinstance(node, ast.Import):
            if any(_HELPER_MODULE in alias.name for alias in node.names):
                return True
    return False


def test_core_layers_never_import_projection_helper():
    offenders = [
        str(py)
        for layer in ("domain", "application")
        for py in (_SRC / layer).rglob("*.py")
        if _imports_helper(py)
    ]
    assert offenders == [], f"projection helper imported by core layers: {offenders}"


# --------------------------------------------------------------------------- #
# S10 / S11 - measured reduction on representative pages
# --------------------------------------------------------------------------- #
def _representative_inbox_page(n=20):
    return [
        raw_inbox(message_id=f"m{i}", delivery_id=f"d{i}", body="x" * 200)
        for i in range(n)
    ]


def test_summary_reduces_at_least_30pct_vs_full():
    items = _representative_inbox_page()
    full = project_page(items, "full", kind="inbox")
    summary = project_page(items, "summary", kind="inbox")
    assert summary["payload_bytes"] <= full["payload_bytes"] * 0.70


def test_default_reduces_vs_full_without_losing_load_bearing():
    items = _representative_inbox_page()
    full = project_page(items, "full", kind="inbox")
    default = project_page(items, "default", kind="inbox")
    assert default["payload_bytes"] < full["payload_bytes"]  # measured > 0
    for it in default["items"]:
        assert "message_id" in it  # load-bearing always present
        assert "delivery_id" in it and "body" in it  # contextuals kept in default
