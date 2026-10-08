"""A blocked SQLite projector must not block durable native ingress."""
import sys
import threading
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from legacy_native_fixture.codex import CodexAppServerConnector

runtime = runtime_fixture


def wait_progress(read, complete, *, stage, stall_seconds, record_property):
    """Bound stalls independently of the duration of a progressing disk backlog."""
    began = advanced = time.monotonic()
    previous = None
    while True:
        value, progress = read()
        now = time.monotonic()
        assert now - began < 30, f"{stage} exceeded campaign bound; last watermark {progress}"
        if complete(value):
            record_property(stage + "_seconds", now - began)
            record_property(stage + "_watermark", progress)
            return value
        if progress != previous:
            previous, advanced = progress, now
        assert now - advanced < stall_seconds, f"{stage} stalled at {progress}"
        time.sleep(.01)
