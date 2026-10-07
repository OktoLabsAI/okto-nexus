"""Server-owned native observations survive persistence without trusting metadata."""
import json
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from legacy_native_fixture.codex import CodexAppServerConnector

runtime = runtime_fixture
