"""Control admission must use session evidence, not the adapter declaration."""
import json
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_effective_requirements import install_versioned_codex
from test_runtime_commands import wait_operation

runtime = runtime_fixture






@pytest.mark.parametrize("version,controls", [("0.85.1", ["steer", "interrupt"]), ("99.0.0", [])])
def test_pi_reports_controls_from_real_owned_version_probe(tmp_path, version, controls):
    from legacy_native_fixture.pi import PiRpcConnector
    from test_harness_pi_connector import _FAKE_SERVER_SOURCE
    peer = PiRpcConnector(command=[sys.executable, "-u", "-c", _FAKE_SERVER_SOURCE],
        version_command=[sys.executable, "-c", "print('" + version + "')"], cwd=str(tmp_path))
    try:
        session = peer.start(owning_agent_id="fixture")
        assert session.compatibility_report["native_version"] == version
        assert session.compatibility_report["compatible_controls"] == controls
        assert session.compatibility_report["capabilities_verified"] is False
    finally:
        peer.close()
