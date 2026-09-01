"""Compatibility guards for the MCP SDK composition boundary."""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("mcp")

from mcp.server.fastmcp.server import Settings

from okto_nexus.adapters.inbound.mcp.server import _load_fastmcp


def test_fastmcp_settings_lifespan_forward_reference_is_rebuilt() -> None:
    """Server creation stays warning-free with pydantic-settings 2.15+."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message=r"Field 'lifespan' has an incomplete definition.*",
        )
        fastmcp = _load_fastmcp()
        fastmcp("probe")

    assert Settings.__pydantic_complete__ is True
    assert Settings.model_fields["lifespan"]._complete is True
