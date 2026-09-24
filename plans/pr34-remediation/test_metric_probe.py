"""Integrity of test-only observations; no provider or personal configuration."""
import json
import sqlite3

import pytest

from runtime_metric_probe import OperationalProbe


def test_missing_capture_cannot_become_a_complete_sample_or_expose_correlation():
    probe = OperationalProbe(limit=1)
    probe.mark("fixture-private-operation", request_start=1, admitted=2)
    probe.mark("second-private-operation", request_start=3)
    result = probe.report()
    assert result["samples"] == []
    assert result["missing_observations"]["durable"] == 1
    assert result["overflow"]
    assert "private-operation" not in json.dumps(result)


def test_failed_sqlite_commit_never_records_durable_enqueue():
    from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork

    probe = OperationalProbe()
    original = SqliteUnitOfWork.commit
    try:
        probe.install()
        connection = sqlite3.connect(":memory:", isolation_level=None)
        uow = SqliteUnitOfWork(connection)
        uow.__enter__()
        uow._metric_probe_enqueues = ["fixture-rolled-back-operation"]
        connection.close()
        with pytest.raises(sqlite3.ProgrammingError):
            uow.commit()
        assert "fixture-rolled-back-operation" not in probe.rows
    finally:
        probe.restore()
    assert SqliteUnitOfWork.commit is original


def test_dispatch_during_commit_return_interval_keeps_a_bound_not_false_precision():
    probe = OperationalProbe()
    probe.mark("fixture-operation", request_start=0, admitted=6000000,
        commit_begin=1000000, commit_end=3000000, dispatch=2000000,
        first_event=3500000, accepted=4000000, terminal=5000000,
        durable=5500000, projected=5800000, dispatch_calls=1)
    result = probe.report()
    assert not result["missing_observations"]
    assert result["samples"][0]["commit_to_dispatch_ms_bounds"] == [0, 1]
    assert result["samples"][0]["terminal_to_durable_ms"] == .5
    assert result["samples"][0]["terminal_to_projected_ms"] == .8
