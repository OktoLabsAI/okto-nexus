"""TC5 - surface + marker tests (spec c7c1f834, TS11 + TS13).

TS11: the ``replay`` pytest marker is registered (no unknown-marker warning) and
selectable. TS13: SURFACE_REVISION stays 24 (no new MCP tool) and
``nexus_info.features`` exposes ``feature_replay`` derived from
FEATURE_FLAG_FIELDS, reflecting the live flag. (Full stdio<->HTTP tool parity is
owned by test_http_parity; here we assert the surface revision + feature echo.)
"""

from __future__ import annotations

import pytest

from okto_nexus.config import FEATURE_FLAG_FIELDS
from okto_nexus.adapters.inbound.mcp.server import SURFACE_REVISION
from okto_nexus.testing import build_hub

pytestmark = pytest.mark.replay


def _ok(env):
    assert env["ok"] is True, env
    return env["data"]


# --------------------------------------------------------------------------- #
# TS11 - marker registered + selectable
# --------------------------------------------------------------------------- #
def test_ts11_replay_marker_is_registered(pytestconfig) -> None:
    markers = pytestconfig.getini("markers")
    assert any(m.split(":", 1)[0].strip() == "replay" for m in markers), (
        f"'replay' marker not registered in {markers!r}"
    )


def test_ts11_this_test_is_collected_under_replay_marker(request) -> None:
    # The module-level pytestmark makes every test here selectable via -m replay;
    # a live marker on this node proves it (no unknown-marker warning is raised).
    assert request.node.get_closest_marker("replay") is not None


# --------------------------------------------------------------------------- #
# TS13 - SURFACE_REVISION locked; nexus_info.features includes feature_replay
# --------------------------------------------------------------------------- #
def test_ts13_surface_revision_unchanged() -> None:
    # I8 shipped no MCP tool (BR7); the surface later moved to 25 when the
    # attachable-policies B3 reshaped agent_whoami/artifact_get (spec 80624c1a),
    # then to 26 when communication presets added the self-only whoami block
    # (spec 6f961722), and ultimately to 33 for adapter-backed artifact payloads
    # plus the HTML artifact type - still no new MCP tool.
    assert SURFACE_REVISION == 33


def test_ts13_feature_replay_is_a_declared_flag() -> None:
    assert "feature_replay" in FEATURE_FLAG_FIELDS


def test_ts13_nexus_info_features_reflect_flag_off() -> None:
    hub = build_hub()  # default: feature_replay OFF
    info = _ok(hub.tools["nexus_info"]())
    assert info["surface_revision"] == 33
    assert "feature_replay" in info["features"]
    assert info["features"]["feature_replay"] is False
    # features are exactly the declared flag fields
    assert set(info["features"]) == set(FEATURE_FLAG_FIELDS)


def test_ts13_nexus_info_features_reflect_flag_on() -> None:
    hub = build_hub({"OKTO_NEXUS_FEATURE_REPLAY": "true"})
    info = _ok(hub.tools["nexus_info"]())
    assert info["features"]["feature_replay"] is True
