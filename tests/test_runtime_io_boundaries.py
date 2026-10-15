"""Observed process, secret, transport and fixture-model IO outside write UoWs."""
import socket
import threading
from collections import Counter
from types import SimpleNamespace

from okto_nexus.adapters.inbound.mcp.tools import harness
from legacy_native_fixture import codex
from okto_nexus.adapters.outbound.embedding import StubEmbeddingProvider
from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
from test_pr34_remediation import runtime as runtime_fixture
from test_runtime_commands import codex_session, wait_operation

runtime = runtime_fixture
