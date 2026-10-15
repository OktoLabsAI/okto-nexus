"""Real disposable Unix peer; unknown wire formats must never receive a token."""
import json
import os

import pytest

from test_claude_code_attach_connector import fake_server as attach_server_fixture, _write_registry, _write_key
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation, wait_close_result
from legacy_native_fixture.claude_code_attach import ClaudeCodeAttachConnector
from okto_nexus.domain.harness import HarnessCommand
from okto_nexus.errors import OktoNexusError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="NOT_RUN: attach requires POSIX ownership")
fake_server = attach_server_fixture
runtime = runtime_fixture
