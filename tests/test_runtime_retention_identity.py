"""Operator retention/deactivation must retain transport exclusion and dedupe."""
import pytest

from okto_nexus.domain.base import iso_plus
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status
from test_runtime_commands import wait_operation, wait_close_result

runtime = runtime_fixture
