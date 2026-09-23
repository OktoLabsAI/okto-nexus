"""Unsupported attach platforms must fail before reading sessions or probing PIDs."""
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.harness import claude_code_attach as attach
from okto_nexus.errors import OktoNexusError


def test_unsupported_attach_has_no_registry_process_or_socket_effects(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("unsupported attach touched registry, process, or socket")

    monkeypatch.setattr(attach, "os", SimpleNamespace(name="nt", kill=forbidden))
    monkeypatch.setattr(attach.socket, "socket", forbidden)
    connector = attach.ClaudeCodeAttachConnector(4242, sessions_dir=tmp_path, env={})
    monkeypatch.setattr(connector, "_read_registry", forbidden)
    monkeypatch.setattr(attach.Path, "glob", forbidden)
    probe = connector.probe()
    assert not probe.ok
    assert probe.reason == "platform_unsupported"
    assert probe.category == "unsupported_platform"
    for action in (
        lambda: connector.start(owning_agent_id="existing-agent"),
        lambda: connector.send(None, None),
        connector._check_process_alive,
        lambda: attach.discover_attachable_sessions(tmp_path),
    ):
        with pytest.raises(OktoNexusError) as error:
            action()
        assert error.value.details["reason"] == "platform_unsupported"


def test_catalog_preserves_attach_and_reports_platform_contract():
    import os
    from okto_nexus.adapters.inbound.mcp.tools.harness import (
        build_connector_factories,
        capabilities_catalog,
    )

    catalog = capabilities_catalog(build_connector_factories(SimpleNamespace()))
    assert len(catalog) == 4
    entry = next(item for item in catalog if item["substrate"] == "attach")
    assert entry["supported_platforms"] == ["posix"]
    assert entry["platform_compatible"] is (os.name == "posix")
    assert entry["capabilities"]["send_only"] is True
    import sys
    for managed in (item for item in catalog if item["substrate"] != "attach"):
        assert managed["supported_platforms"] == ["nt", "linux"]
        assert managed["platform_compatible"] is (os.name == "nt" or sys.platform == "linux")


def test_unsupported_managed_platform_rejects_before_spawn(monkeypatch):
    from okto_nexus.adapters.outbound.harness import owned_process
    monkeypatch.setattr(owned_process, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(owned_process, "sys", SimpleNamespace(platform="darwin"))
    with pytest.raises(OktoNexusError) as error:
        owned_process.spawn_owned_process(["must-not-launch"])
    assert error.value.details["reason"] == "platform_unsupported"
