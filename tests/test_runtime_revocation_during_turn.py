"""Revocation after native acceptance preserves evidence without work authority."""
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import work, wait_result
from test_runtime_work_results import native_work_peer, outcome, state

runtime = runtime_fixture
