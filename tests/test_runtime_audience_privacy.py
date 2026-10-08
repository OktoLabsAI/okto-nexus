"""Runtime delivery and result projection obey both private scope directions."""
import json
import threading

import pytest

from okto_nexus.application.runtime_results import RuntimeResultService
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_commands import codex_session
from test_runtime_result_publication import result

runtime = runtime_fixture
