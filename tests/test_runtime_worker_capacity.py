"""Retained legacy workers stay occupied after a synthetic peer emits a result."""
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_production_multiplex import configure, open_endpoint
from test_runtime_commands import wait_operation

runtime = runtime_fixture
