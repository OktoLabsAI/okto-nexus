"""Real restricted credentials and anonymous HTTP never gain runtime authority."""
import sys

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_grants import issue
from test_poll_tokens import _issue_token

runtime = runtime_fixture
