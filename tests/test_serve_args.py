"""Serve-flag parsing: the console log-level knob (default WARNING, opt-in via
``--log-level``/``OKTO_NEXUS_LOG_LEVEL``, fail-closed on a bad value) lives next
to the existing port/host extraction in ``_split_serve_args``.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.cli.serve import (
    DEFAULT_LOG_LEVEL,
    _split_serve_args,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


def test_log_level_defaults_to_warning():
    port, host, root, level, rest = _split_serve_args([], {})
    assert level == "warning" == DEFAULT_LOG_LEVEL
    assert rest == []


def test_log_level_flag_spaced_and_inline_and_case_normalised():
    _, _, _, level, rest = _split_serve_args(
        ["--log-level", "INFO", "--home", "/tmp/x"], {}
    )
    assert level == "info"
    # Unrelated flags pass straight through to load_config.
    assert rest == ["--home", "/tmp/x"]

    _, _, _, inline, _ = _split_serve_args(["--log-level=Debug"], {})
    assert inline == "debug"


def test_log_level_env_default_and_flag_overrides_env():
    _, _, _, from_env, _ = _split_serve_args([], {"OKTO_NEXUS_LOG_LEVEL": "error"})
    assert from_env == "error"

    _, _, _, flag_wins, _ = _split_serve_args(
        ["--log-level", "trace"], {"OKTO_NEXUS_LOG_LEVEL": "error"}
    )
    assert flag_wins == "trace"


def test_invalid_log_level_fails_closed():
    with pytest.raises(OktoNexusError) as ei:
        _split_serve_args(["--log-level", "loud"], {})
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value
    assert ei.value.details["log_level"] == "loud"
