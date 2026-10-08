"""Concurrent authenticated command admission and immutable request identity."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_commands import wait_operation
from test_runtime_grants import issue

runtime = runtime_fixture


def send(runtime, surface, key, arguments):
    client = runtime[1]
    if surface == "mcp":
        return tool(client, key, "harness_send", arguments)
    body = dict(arguments)
    session = body.pop("session_id")
    response = client.post(f"/api/v1/harness/sessions/{session}/send",
                           headers={"x-api-key": key}, json=body)
    assert response.status_code in {200, 409}, response.text
    return response.json()


def snapshot(runtime):
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        # Transport progress may legitimately change while a repeated request
        # arrives. These are the immutable admission facts, without credentials.
        return [tuple(row) for row in uow.connection.execute(
            "SELECT operation_id,actor_agent_id,idempotency_key,request_hash,"
            "grant_id,runtime_session_id,endpoint_id,endpoint_revision,"
            "profile_revision,verb,payload,expected_owner_epoch,"
            "expected_operation_id,expected_turn_id FROM runtime_commands")]
