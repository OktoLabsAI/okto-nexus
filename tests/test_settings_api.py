"""Runtime settings: catalogue, validation, persistence, CLI pinning."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.application.settings import SETTING_SPECS  # noqa: E402


@pytest.fixture
def loopback_client(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        yield deps, client


def test_settings_catalogue_lists_every_spec_with_description(loopback_client):
    _, client = loopback_client
    items = client.get("/api/v1/settings").json()["data"]["items"]
    by_key = {item["key"]: item for item in items}
    assert set(by_key) == {spec.key for spec in SETTING_SPECS}
    for item in items:
        assert item["description"]  # the tooltip text is mandatory
        assert item["source"] == "default"
        assert item["editable"] is True
        assert item["value"] == item["default"]


def test_patch_persists_and_applies_to_live_config(loopback_client):
    deps, client = loopback_client
    response = client.patch(
        "/api/v1/settings", json={"session_stale_ttl_seconds": 120}
    )
    assert response.status_code == 200
    # Applied to the LIVE config object (presence derivation uses it now).
    assert deps.config.session_stale_ttl_seconds == 120
    # Persisted: a fresh bootstrap over the same home picks it up.
    deps2 = bootstrap({}, ["--home", str(deps.config.home_dir)])
    app2 = build_app(deps2)
    with TestClient(app2, client=("127.0.0.1", 50001)):
        assert deps2.config.session_stale_ttl_seconds == 120


def test_meta_harness_receipt_display_defaults_inline_and_persists(loopback_client):
    deps, client = loopback_client
    items = client.get("/api/v1/settings").json()["data"]["items"]
    setting = next(
        item for item in items if item["key"] == "meta_harness_receipt_display"
    )
    assert setting == {
        "key": "meta_harness_receipt_display",
        "type": "enum",
        "group": "interface",
        "description": setting["description"],
        "value": "inline",
        "default": "inline",
        "min": None,
        "max": None,
        "choices": ["inline", "timeline"],
        "source": "default",
        "editable": True,
        "requires_restart": False,
    }

    response = client.patch(
        "/api/v1/settings", json={"meta_harness_receipt_display": "timeline"}
    )
    assert response.status_code == 200
    assert deps.config.meta_harness_receipt_display == "timeline"

    deps2 = bootstrap({}, ["--home", str(deps.config.home_dir)])
    app2 = build_app(deps2)
    with TestClient(app2, client=("127.0.0.1", 50003)):
        assert deps2.config.meta_harness_receipt_display == "timeline"


def test_patch_rejects_out_of_range_unknown_and_bad_enum(loopback_client):
    _, client = loopback_client
    assert (
        client.patch("/api/v1/settings", json={"session_stale_ttl_seconds": 1})
        .status_code
        == 422
    )
    assert (
        client.patch("/api/v1/settings", json={"nope": 1}).status_code == 422
    )
    assert (
        client.patch("/api/v1/settings", json={"trust_mode": "yolo"}).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/v1/settings",
            json={"meta_harness_receipt_display": "popup"},
        ).status_code
        == 422
    )


def test_cli_pinned_setting_is_read_only(tmp_path):
    deps = bootstrap(
        {}, ["--home", str(tmp_path / "home"), "--session-stale-ttl-seconds", "90"]
    )
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50002)) as client:
        items = client.get("/api/v1/settings").json()["data"]["items"]
        pinned = next(i for i in items if i["key"] == "session_stale_ttl_seconds")
        assert pinned["source"] == "cli/env"
        assert pinned["editable"] is False
        assert pinned["value"] == 90
        # And the API refuses to shadow it.
        response = client.patch(
            "/api/v1/settings", json={"session_stale_ttl_seconds": 200}
        )
        assert response.status_code == 422
        assert deps.config.session_stale_ttl_seconds == 90


def test_settings_reset_restores_defaults(loopback_client):
    deps, client = loopback_client
    client.patch("/api/v1/settings", json={"presence_ttl_seconds": 900})
    assert deps.config.presence_ttl_seconds == 900
    response = client.post("/api/v1/settings/reset")
    assert response.status_code == 200
    assert deps.config.presence_ttl_seconds == 1800  # default restored
    items = client.get("/api/v1/settings").json()["data"]["items"]
    assert all(item["source"] == "default" for item in items)
