"""Production serve cleanup, authenticated approved Pi fixture, exact process witnesses."""
import os
import pytest
from runtime_serve_shutdown_fixture import ServeFixture


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
        server.open()
        server.close_session()
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
