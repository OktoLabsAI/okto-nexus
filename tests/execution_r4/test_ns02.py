"""Namespace isolation for future durable R4 execution tables."""

import pytest

from okto_nexus.domain.execution.keys import (
    ApprovalKey, BindingKey, ExecutorKey, SessionKey,
    SessionOwnerGeneration, StreamKey,
)


def test_ns02_01():
    left = ExecutorKey("server-a", "executor")
    right = ExecutorKey("server-b", "executor")
    assert left != right
    bindings = {
        BindingKey("server-a", "executor", "same"): "left",
        BindingKey("server-b", "executor", "same"): "right",
    }
    sessions = {
        SessionKey("server-a", "executor", "same"): "left",
        SessionKey("server-b", "executor", "same"): "right",
    }
    streams = {
        StreamKey("server-a", "executor", "same", "epoch"): "left",
        StreamKey("server-b", "executor", "same", "epoch"): "right",
    }
    approvals = {
        ApprovalKey("server-a", "executor", "same", "agent", "ws", "same",
                    SessionOwnerGeneration(1), "request", "native"): "left",
        ApprovalKey("server-b", "executor", "same", "agent", "ws", "same",
                    SessionOwnerGeneration(1), "request", "native"): "right",
    }
    for mapping in (bindings, sessions, streams, approvals):
        left_key = next(key for key in mapping if key.server_id == "server-a")
        del mapping[left_key]
        assert len(mapping) == 1
        assert next(iter(mapping)).server_id == "server-b"
    with pytest.raises((TypeError, ValueError)):
        ApprovalKey("server-a", "executor", "same", "agent", "ws", "same",
                    1, "request", "native")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SessionKey("server-a", "executor", "x" * 161)
