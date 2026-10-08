"""Activation preserves old logical inbox work and has one transport executor."""
import json
from pathlib import Path
import sys
import threading
import time

from fastapi.testclient import TestClient
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_commands import wait_close_result, wait_operation

runtime = runtime_fixture
