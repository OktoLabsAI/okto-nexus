"""Canonical inbox stays exclusive after acceptance or uncertain transport."""
import json
import socket
import time

import pytest

from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.runtime_commands import RuntimeCommandNotSent
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_commands import codex_session
from test_runtime_handoff_dispatch import wait_result
from test_runtime_outbox import operation, wait_status

runtime = runtime_fixture


def worker_key(runtime):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work() as uow:
        return AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")


def pull(runtime, key):
    result = tool(runtime[1], key, "inbox_pull", {"agent_id": "worker"})
    assert result["ok"], result
    return result["data"]["messages"]
