"""Canonical bootstrap reaches the actual connector without private authority."""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import work, claim

runtime = runtime_fixture
