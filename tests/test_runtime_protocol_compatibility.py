"""Protocol drift cannot publish a false ready binding in production composition."""
import json
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from legacy_native_fixture.pi import PiRpcConnector
from legacy_native_fixture.codex import CodexAppServerConnector

runtime = runtime_fixture
