"""Production serve cleanup, authenticated approved Pi fixture, exact process witnesses."""
import os
import pytest
from runtime_serve_shutdown_fixture import ServeFixture
from test_pr34_remediation import tool
from test_runtime_commands import wait_close_result


@pytest.mark.skipif(os.name != "posix", reason="POSIX SIGTERM; Windows owned process termination tested separately")
def test_sigterm_with_live_session_reaps_the_harness_child(tmp_path):
    server = ServeFixture(tmp_path)
    try:
        server.open()
        server.stop("term")
    finally:
        server.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX SIGINT; Windows graceful server exit tested separately")
def test_sigint_with_live_session_reaps_the_harness_child(tmp_path):
    server = ServeFixture(tmp_path)
    try:
        server.open()
        server.stop("int")
    finally:
        server.close()


def test_clean_shutdown_after_explicit_close_leaves_no_orphan(tmp_path):
    server = ServeFixture(tmp_path)
    try:
        sid = server.open()
        wait_close_result(server.client, server.operator, tool(server.client, server.operator, "harness_close", {"session_id": sid}))
        for witness in server.witnesses:
            witness.assert_stopped()
        server.stop("clean")
        assert server.process.returncode == 0
    finally:
        server.close()


def test_clean_shutdown_with_live_session_reaps_child_and_grandchild(tmp_path):
    server = ServeFixture(tmp_path)
    try:
        server.open()
        server.stop("clean")
        assert server.process.returncode == 0
    finally:
        server.close()
