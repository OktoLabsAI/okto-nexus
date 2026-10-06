from types import SimpleNamespace

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from okto_nexus.config import NexusConfig
from okto_nexus.adapters.inbound.http.executor_link import _safe_transport
from okto_nexus.adapters.inbound.http.transport_security import TransportSecurityMiddleware


@pytest.mark.parametrize("mode,secure,allowed", [
    ("http_https", False, True), ("http_https", True, True),
    ("https_only", False, False), ("https_only", True, True),
])
def test_remote_http_and_websocket_share_transport_policy(mode, secure, allowed):
    config = NexusConfig(transport_security=mode)
    app = FastAPI()
    app.state.deps = SimpleNamespace(config=config)
    app.add_middleware(TransportSecurityMiddleware, config=config)

    @app.get("/probe")
    def probe():
        return {"ok": True}

    @app.websocket("/link")
    async def link(ws: WebSocket):
        assert _safe_transport(ws)
        await ws.accept()
        await ws.send_text("accepted")
        await ws.close()

    scheme = "https" if secure else "http"
    with TestClient(app, base_url=f"{scheme}://192.168.0.146:8202",
                    client=("192.168.0.116", 50000)) as client:
        response = client.get("/probe", headers={"X-Forwarded-Proto": "https"})
        assert response.status_code == (200 if allowed else 403)
        if not allowed:
            assert response.json()["error"]["code"] == "TLS_REQUIRED"
        url = f"{'wss' if secure else 'ws'}://192.168.0.146:8202/link"
        if allowed:
            with client.websocket_connect(url) as ws:
                assert ws.receive_text() == "accepted"
        else:
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect(url):
                    pass
            assert error.value.code == 4406


@pytest.mark.parametrize("origin,allowed", [
    (None, True), ("http://192.168.0.146:8202", True),
    ("http://other-host:8202", False), ("https://192.168.0.146:8202", False),
])
def test_plain_remote_websocket_keeps_origin_validation(origin, allowed):
    app = SimpleNamespace(state=SimpleNamespace(deps=SimpleNamespace(config=NexusConfig())))
    ws = WebSocket({"type": "websocket", "scheme": "ws", "path": "/link",
        "query_string": b"", "server": ("192.168.0.146", 8202),
        "client": ("192.168.0.116", 50000), "app": app,
        "headers": [] if origin is None else [(b"origin", origin.encode())]},
        receive=None, send=None)
    assert _safe_transport(ws) is allowed
