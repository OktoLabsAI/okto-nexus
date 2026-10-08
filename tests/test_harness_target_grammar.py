"""Canonical target routing through authenticated production serve.

Legacy callback/TTL relay assertions are covered by test_runtime_relay,
test_runtime_causality and test_runtime_relay_process_restart. See the explicit
migration map in P11_TARGET_GRAMMAR_MIGRATION.md; no implicit Agent registration.
"""
import json
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status

runtime = runtime_fixture
