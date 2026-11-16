"""Packaged dashboard assets and Home contracts use the installed HTTP app.

The installed runner separately proves wheel payload/origin equality. This test
uses a disposable home, no provider discovery and no development web server.
"""
from html.parser import HTMLParser
from importlib.resources import files
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap import dependencies, embedded_inventory


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        path = values.get("src") if tag == "script" else values.get("href") if tag == "link" else None
        if path and (tag == "script" or values.get("rel") == "stylesheet"):
            self.paths.append(path)


def test_packaged_operational_home_serves_assets_and_compatible_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    deps = dependencies.bootstrap({}, ["--home", str(tmp_path / "home"),
        "--feature-harness-integrations", "false", "--embedding-mode", "off"])
    app = build_app(deps)
    static = files("okto_nexus").joinpath("adapters/inbound/http/static")
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://localhost") as client:
        index = client.get("/")
        assert index.status_code == 200
        assert index.content == static.joinpath("index.html").read_bytes()
        parser = AssetReferences()
        parser.feed(index.text)
        assert any(path.endswith(".js") for path in parser.paths)
        assert any(path.endswith(".css") for path in parser.paths)
        for path in parser.paths:
            parsed = urlsplit(path)
            assert not parsed.scheme and not parsed.netloc and not parsed.query
            assert parsed.path.startswith("/assets/") and ".." not in parsed.path.split("/")
            resource = client.get(path)
            assert resource.status_code == 200
            assert resource.content == static.joinpath(parsed.path.lstrip("/")).read_bytes()
        assert client.get("/assets/home-missing-file.js").status_code == 404
        overview = client.get("/api/v1/home/overview")
        assert overview.status_code == 200
        assert overview.headers["cache-control"] == "no-store"
        value = overview.json()["data"]
        assert value["version"] == 1 and value["server_id"]
        assert value["scope"] == {"workspace_id": None}
        assert {"work", "results", "attention", "agents", "external_activity"} <= value.keys()
        assert {"running", "waiting_start", "needs_you", "results"} <= value["summary"].keys()
        schema = client.get("/api/v1/openapi.json").json()
        assert "get" in schema["paths"]["/api/v1/home/overview"]
        assert "post" not in schema["paths"]["/api/v1/home/overview"]
        assert "post" in schema["paths"]["/v1/runtime/operations"]
