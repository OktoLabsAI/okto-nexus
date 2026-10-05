"""MCP stdio is absent from both console and legacy Python entry points."""

from __future__ import annotations

from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.inbound.mcp.server import main as legacy_main


def test_no_arguments_shows_http_help(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "serve" in output and "HTTP" in output and "/mcp" in output
    assert "stdio" not in output.lower()


def test_old_flags_and_explicit_stdio_fail_without_bootstrap(monkeypatch, capsys):
    import okto_nexus.adapters.inbound.mcp.server as server

    monkeypatch.setattr(server, "bootstrap", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("bootstrap called")))
    for args in (["--home", "somewhere"], ["stdio"], ["mcp"]):
        assert main(args) == 2
        assert legacy_main(args) == 2
    assert "HTTP /mcp" in capsys.readouterr().err
