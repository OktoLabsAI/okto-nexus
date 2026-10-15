"""A pull competing with canonical push admission cannot see its payload."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent
from test_runtime_consumption_acceptance import worker_key, pull

runtime = runtime_fixture
