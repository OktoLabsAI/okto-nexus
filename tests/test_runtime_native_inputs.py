"""Explicit human answers, never implicit data from a binary approval."""
import json
import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_native_approvals import approval_peer, pending
from test_runtime_handoff_dispatch import wait_result

runtime = runtime_fixture

QUESTION = {"isBlocking": True, "questions": [{"id": "color", "header": "Color", "question": "Choose fixture color",
    "isOther": False, "isSecret": False, "options": [{"label": "blue", "description": "Fixture only"}]}]}




FORM = {"mode": "form", "serverName": "fixture", "message": "Choose fixture options",
    "requestedSchema": {"type": "object", "properties": {
        "color": {"type": "string", "enum": ["blue", "green"]},
        "count": {"type": "integer", "minimum": 1, "maximum": 3},
        "enabled": {"type": "boolean"}}, "required": ["color", "count", "enabled"]}}
