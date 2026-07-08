"""Tests for R-I0: meta-harness feature flags.

The 7 ``feature_*`` knobs are plain ``NexusConfig`` bool fields registered in
``_BOOL_FIELDS`` (env ``OKTO_NEXUS_FEATURE_*``, CLI ``--feature-*``) and in
``SETTING_SPECS`` (group ``features``), so they inherit the whole existing
pipeline: fail-closed coercion, CLI > env > stored > default precedence,
pinning, REST GET/PATCH persistence and the ``nexus_info`` surface.

Spec: 0cd33b60 (board 28585c8d) - scenarios TS1..TS7.
"""

from __future__ import annotations

import pytest

from okto_nexus.config import NexusConfig, load_config
from okto_nexus.errors import ErrorCode, OktoNexusError

#: (NexusConfig field, env var, CLI flag) for the 7 meta-harness flags.
#: feature_governance was removed (spec 80624c1a, D-FLAG): policy enforcement is
#: always-on and binding-driven, no longer flag-gated.
FEATURE_FLAGS = [
    ("feature_trace", "OKTO_NEXUS_FEATURE_TRACE", "--feature-trace"),
    ("feature_hitl", "OKTO_NEXUS_FEATURE_HITL", "--feature-hitl"),
    (
        "feature_verification",
        "OKTO_NEXUS_FEATURE_VERIFICATION",
        "--feature-verification",
    ),
    ("feature_dag", "OKTO_NEXUS_FEATURE_DAG", "--feature-dag"),
    ("feature_memory", "OKTO_NEXUS_FEATURE_MEMORY", "--feature-memory"),
    ("feature_health", "OKTO_NEXUS_FEATURE_HEALTH", "--feature-health"),
    ("feature_replay", "OKTO_NEXUS_FEATURE_REPLAY", "--feature-replay"),
]

FEATURE_FIELDS = [field for field, _, _ in FEATURE_FLAGS]


# --------------------------------------------------------------------------- #
# C1 - config core (TS5 + defaults half of TS1)
# --------------------------------------------------------------------------- #
def test_all_feature_flags_default_false():
    """Opt-in contract (BR1): with no override anywhere, every flag is OFF."""
    config = load_config({})
    for field in FEATURE_FIELDS:
        assert getattr(config, field) is False, field
        assert getattr(NexusConfig(), field) is False, field


@pytest.mark.parametrize("field,env_var,flag", FEATURE_FLAGS)
def test_feature_flag_env_true(field, env_var, flag):
    config = load_config({env_var: "true"})
    assert getattr(config, field) is True
    # Only the targeted flag flips; the other seven stay at their default.
    for other in FEATURE_FIELDS:
        if other != field:
            assert getattr(config, other) is False, other


@pytest.mark.parametrize("spelling", ["true", "1", "yes", "on", " TRUE "])
def test_feature_flag_accepts_bool_spellings(spelling):
    config = load_config({"OKTO_NEXUS_FEATURE_TRACE": spelling})
    assert config.feature_trace is True


@pytest.mark.parametrize("spelling", ["false", "0", "no", "off"])
def test_feature_flag_false_spellings(spelling):
    config = load_config({"OKTO_NEXUS_FEATURE_TRACE": spelling})
    assert config.feature_trace is False


@pytest.mark.parametrize("field,env_var,flag", FEATURE_FLAGS)
def test_feature_flag_cli_overrides_env(field, env_var, flag):
    config = load_config({env_var: "true"}, [flag, "false"])
    assert getattr(config, field) is False  # CLI > env precedence


@pytest.mark.parametrize("bad", ["maybe", "enabled", "", "  ", "2"])
def test_feature_flag_invalid_env_aborts_with_config_error(bad):
    """TS5 (BR3): a non-boolean value aborts the fail-closed bootstrap with
    CONFIG_ERROR - it must never silently coerce to a default."""
    with pytest.raises(OktoNexusError) as ei:
        load_config({"OKTO_NEXUS_FEATURE_TRACE": bad})
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value
    assert "feature_trace" in ei.value.message


def test_feature_flag_invalid_cli_aborts_with_config_error():
    with pytest.raises(OktoNexusError) as ei:
        load_config({}, ["--feature-dag", "banana"])
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value
    assert "feature_dag" in ei.value.message


# --------------------------------------------------------------------------- #
# C2 - SETTING_SPECS group "features": REST inheritance (TS1..TS4, REST half)
# --------------------------------------------------------------------------- #
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.application.settings import SETTING_SPECS  # noqa: E402


@pytest.fixture
def loopback_client(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50100)) as client:
        yield deps, client


def test_setting_specs_register_the_7_flags_in_the_features_group():
    by_key = {spec.key: spec for spec in SETTING_SPECS}
    for field in FEATURE_FIELDS:
        spec = by_key[field]
        assert spec.type == "bool", field
        assert spec.group == "features", field
        assert spec.requires_restart is (field == "feature_memory"), field
        assert spec.description, field
    # Pre-existing knobs keep the default group: the new field is additive.
    assert by_key["session_stale_ttl_seconds"].group == "general"


def test_settings_catalogue_lists_features_with_defaults(loopback_client):
    """TS1 (REST half): clean environment -> 7 items, all off, editable."""
    _, client = loopback_client
    items = client.get("/api/v1/settings").json()["data"]["items"]
    features = [i for i in items if i["group"] == "features"]
    assert {i["key"] for i in features} == set(FEATURE_FIELDS)
    for item in features:
        assert item["type"] == "bool"
        assert item["value"] is False
        assert item["default"] is False
        assert item["source"] == "default"
        assert item["editable"] is True
        assert item["requires_restart"] is (item["key"] == "feature_memory")


def test_patch_feature_flag_persists_and_applies_live(loopback_client):
    """TS2 (REST half): PATCH -> 200, live config mutated, stored survives
    a fresh bootstrap over the same home."""
    deps, client = loopback_client
    response = client.patch("/api/v1/settings", json={"feature_trace": True})
    assert response.status_code == 200
    assert deps.config.feature_trace is True  # applied without restart
    items = client.get("/api/v1/settings").json()["data"]["items"]
    stored = next(i for i in items if i["key"] == "feature_trace")
    assert stored["value"] is True
    assert stored["source"] == "stored"
    # Persisted: a fresh bootstrap over the same home picks it up.
    deps2 = bootstrap({}, ["--home", str(deps.config.home_dir)])
    app2 = build_app(deps2)
    with TestClient(app2, client=("127.0.0.1", 50101)):
        assert deps2.config.feature_trace is True


def test_env_pinned_feature_flag_is_read_only(tmp_path):
    """TS3: a flag set via env is pinned - source cli/env, PATCH refused."""
    deps = bootstrap(
        {"OKTO_NEXUS_FEATURE_DAG": "true"}, ["--home", str(tmp_path / "home")]
    )
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50102)) as client:
        items = client.get("/api/v1/settings").json()["data"]["items"]
        pinned = next(i for i in items if i["key"] == "feature_dag")
        assert pinned["value"] is True
        assert pinned["source"] == "cli/env"
        assert pinned["editable"] is False
        response = client.patch("/api/v1/settings", json={"feature_dag": False})
        assert response.status_code == 422
        assert deps.config.feature_dag is True  # unchanged


def test_patch_feature_flag_rejects_bad_value_and_unknown_key(loopback_client):
    """TS4: non-boolean value and unknown feature_* key -> 422, no mutation."""
    deps, client = loopback_client
    response = client.patch("/api/v1/settings", json={"feature_memory": "banana"})
    assert response.status_code == 422
    assert deps.config.feature_memory is False
    response = client.patch("/api/v1/settings", json={"feature_unknown": True})
    assert response.status_code == 422
    items = client.get("/api/v1/settings").json()["data"]["items"]
    assert "feature_unknown" not in {i["key"] for i in items}
    untouched = next(i for i in items if i["key"] == "feature_memory")
    assert untouched["value"] is False
    assert untouched["source"] == "default"


# --------------------------------------------------------------------------- #
# C3 - nexus_info.features + SURFACE_REVISION 17 (TS6 + nexus_info half of
# TS1/TS2)
# --------------------------------------------------------------------------- #
import asyncio  # noqa: E402
import json  # noqa: E402

pytest.importorskip("mcp")
from okto_nexus.adapters.inbound.http.app import create_http_mcp_server  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import (  # noqa: E402
    SURFACE_REVISION,
    create_server,
)
from okto_nexus.config import FEATURE_FLAG_FIELDS  # noqa: E402


def _call(server, name: str, arguments: dict | None = None) -> dict:
    result = asyncio.run(server.call_tool(name, arguments or {}))
    if isinstance(result, tuple):
        return result[1]
    return json.loads(result[0].text)


def test_feature_flag_fields_constant_matches_the_7_flags():
    assert set(FEATURE_FLAG_FIELDS) == set(FEATURE_FIELDS)


def test_nexus_info_features_identical_on_stdio_and_http(tmp_path):
    """TS6: the features block is identical across transports, with exactly
    the 7 keys, and surface_revision is 29 on both."""
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    stdio_env = _call(create_server(deps), "nexus_info")
    http_env = _call(create_http_mcp_server(deps), "nexus_info")

    stdio_info = stdio_env["data"] if "data" in stdio_env else stdio_env
    http_info = http_env["data"] if "data" in http_env else http_env

    assert stdio_info["features"] == http_info["features"]
    assert set(stdio_info["features"]) == set(FEATURE_FIELDS)
    assert all(value is False for value in stdio_info["features"].values())
    assert stdio_info["surface_revision"] == 29
    assert http_info["surface_revision"] == 29
    assert SURFACE_REVISION == 29


def test_nexus_info_reflects_env_pinned_flag(tmp_path):
    deps = bootstrap(
        {"OKTO_NEXUS_FEATURE_HEALTH": "true"}, ["--home", str(tmp_path / "home")]
    )
    envelope = _call(create_server(deps), "nexus_info")
    info = envelope["data"] if "data" in envelope else envelope
    assert info["features"]["feature_health"] is True
    others = {k: v for k, v in info["features"].items() if k != "feature_health"}
    assert all(value is False for value in others.values())


def test_nexus_info_reflects_patch_without_restart(loopback_client):
    """TS2 (nexus_info half): flipping a flag via PATCH shows up in the SAME
    process - the block reads the live config, not a boot snapshot."""
    deps, client = loopback_client
    server = create_server(deps)
    before = _call(server, "nexus_info")
    info_before = before["data"] if "data" in before else before
    assert info_before["features"]["feature_trace"] is False

    assert (
        client.patch("/api/v1/settings", json={"feature_trace": True}).status_code
        == 200
    )
    after = _call(server, "nexus_info")
    info_after = after["data"] if "data" in after else after
    assert info_after["features"]["feature_trace"] is True
