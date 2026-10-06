import socket

from starlette.testclient import TestClient

from okto_nexus.adapters.inbound.http.mcp_security import mcp_transport_security
from okto_nexus.adapters.inbound.mcp.registration import _load_fastmcp


def test_lan_mcp_initialize_and_untrusted_host_origin(monkeypatch):
    monkeypatch.setattr(socket, "gethostname", lambda: "nexus-server")
    monkeypatch.setattr(socket, "getfqdn", lambda: "nexus-server")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: [(2, 1, 6, "", ("192.168.0.146", 0))])
    server = _load_fastmcp()("test", stateless_http=True,
        transport_security=mcp_transport_security("0.0.0.0", 8202))
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "regression", "version": "1"}}}
    headers = {"accept": "application/json, text/event-stream"}
    with TestClient(server.streamable_http_app(), base_url="http://192.168.0.146:8202") as client:
        response = client.post("/mcp", json=body, headers=headers)
        assert response.status_code == 200
        assert "serverInfo" in response.text
        assert client.post("/mcp", json=body, headers={**headers, "host": "attacker.example:8202"}).status_code == 421
        assert client.post("/mcp", json=body, headers={**headers, "origin": "http://attacker.example"}).status_code == 403
        assert client.post("/mcp", json=body, headers={**headers, "host": "192.168.0.146:9999"}).status_code == 421


def test_loopback_does_not_admit_lan():
    settings = mcp_transport_security("127.0.0.1", 8202)
    assert settings.enable_dns_rebinding_protection
    assert "127.0.0.1:8202" in settings.allowed_hosts
    assert "192.168.0.146:8202" not in settings.allowed_hosts


def test_explicit_bind_host():
    settings = mcp_transport_security("192.168.0.146", 8202)
    assert "192.168.0.146:8202" in settings.allowed_hosts
    assert "http://192.168.0.146:8202" in settings.allowed_origins
