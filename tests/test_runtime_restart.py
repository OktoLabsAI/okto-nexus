"""Recovery uses the production composition and real native fixture pipes."""
import sys
import time

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.harness import build_dispatcher
from legacy_native_fixture.codex import CodexAppServerConnector
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, send_message, open_rest
from test_runtime_outbox import operation, wait_status

runtime = runtime_fixture
