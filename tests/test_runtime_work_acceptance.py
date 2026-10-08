"""Remaining work acceptance stimuli through production HTTP/MCP and native pipes."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import claim, work

runtime = runtime_fixture
