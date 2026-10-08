"""Canonical catalogue gates and owned-process cleanup after partial startup."""
import sqlite3
import sys

import pytest

from legacy_native_fixture.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_close_result

runtime = runtime_fixture


def identities(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        # Authentication updates caller activity independently of runtime start.
        # Compare all identity/profile fields except this observation timestamp.
        return [{key: row[key] for key in row.keys() if key != "last_seen_at"}
            for row in uow.connection.execute("SELECT * FROM agents ORDER BY agent_id")]
