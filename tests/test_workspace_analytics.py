"""WorkspaceAnalyticsService: bucket derivation, nearest-rank p95, top-8+others,
strict workspace isolation and bounded truncation.

Deterministic by construction: a FakeClock pins "now" so the bucket grid is
fixed, and a FakeTokenizer counts tokens = body length so every token total /
p95 is hand-verifiable. The real tiktoken path is exercised end-to-end by the
HTTP test card (T5/T6); here we prove the AGGREGATION maths in isolation.

Scenario coverage (spec bf6e06dc):
* S3/AC3 - 24h: bucket_seconds=3600, 24 buckets (zeros included), summary
* S4/AC3 - 7d->21600s/28 buckets, 30d->86400s/30 buckets
* S8/AC7/BR4 - isolation: workspace A analytics excludes workspace B
* S9/AC8/BR10 - bounded: top-8 + others in agents[] and per bucket; truncation
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.outbound.sqlite.observability_repo import (
    SqliteObservabilityQueries,
)
from okto_nexus.application.workspace_analytics import (
    ANALYTICS_MAX_MESSAGES,
    WINDOWS,
    WorkspaceAnalyticsService,
    _epoch_to_iso,
    is_valid_window,
    p95_nearest_rank,
)
from okto_nexus.domain.base import iso_to_epoch, new_id

NOW_ISO = "2026-06-19T12:30:00.000000Z"
NOW_EPOCH = iso_to_epoch(NOW_ISO)
HOUR = 3600


class FakeClock:
    def __init__(self, epoch: float) -> None:
        self._e = epoch

    def now_epoch(self) -> float:
        return self._e

    def now_iso(self) -> str:
        return _epoch_to_iso(self._e)


class FakeTokenizer:
    """tokens == len(body); deterministic so totals/p95 are hand-checkable."""

    encoding = "fake-len"

    def count(self, text):
        return len(text) if text else 0

    def count_for_message(self, message_id, body):
        return self.count(body)


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def deps(tmp_path):
    return bootstrap({}, ["--home", str(tmp_path / "home")])


def setup_workspace(deps, ws):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)


def setup_agents(deps, *agents):
    with deps.connection_factory.unit_of_work() as uow:
        for a in agents:
            deps.repos.agents.upsert(uow, agent_id=a)


def seed_message(deps, *, ws, agent, body, at_epoch):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.messages.create(
            uow,
            message_id=new_id("msg"),
            workspace_id=ws,
            from_agent_id=agent,
            body=body,
            created_at=_epoch_to_iso(at_epoch),
        )


def make_service(deps, *, clock=None, tokenizer=None, max_messages=ANALYTICS_MAX_MESSAGES):
    return WorkspaceAnalyticsService(
        connection_factory=deps.connection_factory,
        queries=SqliteObservabilityQueries(),
        tokenizer=tokenizer or FakeTokenizer(),
        clock=clock or FakeClock(NOW_EPOCH),
        max_messages=max_messages,
    )


# --------------------------------------------------------------------------- #
# p95 nearest-rank (pure unit)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "values,expected",
    [
        ([], 0),
        ([7], 7),
        (list(range(1, 11)), 10),   # ceil(0.95*10)=10 -> idx 9 -> 10
        (list(range(1, 21)), 19),   # ceil(0.95*20)=19 -> idx 18 -> 19
        ([5, 1, 3, 2, 4], 5),       # sorted [1..5], ceil(4.75)=5 -> 5
    ],
)
def test_p95_nearest_rank(values, expected):
    assert p95_nearest_rank(values) == expected


def test_window_validation():
    assert is_valid_window("24h") and is_valid_window("7d") and is_valid_window("30d")
    assert not is_valid_window("99h")
    assert not is_valid_window(None)


# --------------------------------------------------------------------------- #
# S3 / AC3 - 24h buckets + summary
# --------------------------------------------------------------------------- #
def test_analytics_24h_buckets_and_summary(deps):
    ws = "ws-a"
    setup_workspace(deps, ws)
    setup_agents(deps, "A", "B")
    # current bucket [12:00,13:00): A sends "xxx"(3) and "xxxxx"(5) tokens
    seed_message(deps, ws=ws, agent="A", body="xxx", at_epoch=NOW_EPOCH - 25 * 60)
    seed_message(deps, ws=ws, agent="A", body="xxxxx", at_epoch=NOW_EPOCH - 15 * 60)
    # previous bucket [11:00,12:00): B sends "xx"(2) tokens, at 11:30
    seed_message(deps, ws=ws, agent="B", body="xx", at_epoch=NOW_EPOCH - 60 * 60)

    data = make_service(deps).analytics(workspace_id=ws, window="24h")

    assert data["window"] == "24h"
    assert data["bucket_seconds"] == 3600
    assert len(data["buckets"]) == 24
    assert data["truncated"] is False
    assert data["scanned_messages"] == 3

    # The current bucket is the LAST one (ends at the bucket containing now).
    current = data["buckets"][-1]
    assert current["total_count"] == 2
    assert current["total_tokens"] == 8
    assert current["by_agent"] == {"A": {"count": 2, "tokens": 8}}

    prev = data["buckets"][-2]
    assert prev["total_count"] == 1
    assert prev["total_tokens"] == 2
    assert prev["by_agent"] == {"B": {"count": 1, "tokens": 2}}

    # All earlier buckets are present and zero.
    assert all(b["total_count"] == 0 for b in data["buckets"][:-2])

    s = data["summary"]
    assert s["total_messages"] == 3
    assert s["total_tokens"] == 10
    assert s["avg_tokens_per_msg"] == pytest.approx(10 / 3)
    assert s["p95_tokens"] == 5  # sorted [2,3,5], ceil(2.85)=3 -> idx2 -> 5
    assert s["peak_bucket_start"] == current["bucket_start"]

    agents = {a["agent_id"]: a for a in data["agents"]}
    assert agents["A"]["count"] == 2 and agents["A"]["tokens"] == 8
    assert agents["A"]["avg_tokens"] == pytest.approx(4.0)
    assert agents["A"]["p95_tokens"] == 5  # [3,5] -> ceil(1.9)=2 -> idx1 -> 5
    assert agents["B"]["tokens"] == 2
    assert data["others"] is None


# --------------------------------------------------------------------------- #
# S4 / AC3 - 7d and 30d derived bucket sizes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "window,bucket_seconds,n_buckets",
    [("7d", 21600, 28), ("30d", 86400, 30)],
)
def test_derived_bucket_sizes(deps, window, bucket_seconds, n_buckets):
    ws = "ws-w"
    setup_workspace(deps, ws)
    setup_agents(deps, "A")
    seed_message(deps, ws=ws, agent="A", body="hello", at_epoch=NOW_EPOCH - 3600)

    data = make_service(deps).analytics(workspace_id=ws, window=window)
    assert data["bucket_seconds"] == bucket_seconds
    assert len(data["buckets"]) == n_buckets
    # bucket grid is contiguous and aligned to bucket_seconds.
    starts = [iso_to_epoch(b["bucket_start"]) for b in data["buckets"]]
    assert all(s % bucket_seconds == 0 for s in starts)
    assert all(
        starts[i + 1] - starts[i] == bucket_seconds for i in range(len(starts) - 1)
    )
    assert WINDOWS[window] == (bucket_seconds * n_buckets, bucket_seconds)


# --------------------------------------------------------------------------- #
# S8 / AC7 / BR4 - strict workspace isolation
# --------------------------------------------------------------------------- #
def test_workspace_isolation(deps):
    setup_workspace(deps, "ws-a")
    setup_workspace(deps, "ws-b")
    setup_agents(deps, "shared")
    seed_message(deps, ws="ws-a", agent="shared", body="aaaa", at_epoch=NOW_EPOCH - 600)
    seed_message(deps, ws="ws-b", agent="shared", body="bbbbbbbb", at_epoch=NOW_EPOCH - 600)

    a = make_service(deps).analytics(workspace_id="ws-a", window="24h")
    b = make_service(deps).analytics(workspace_id="ws-b", window="24h")

    assert a["summary"]["total_messages"] == 1
    assert a["summary"]["total_tokens"] == 4  # only ws-a's "aaaa"
    assert b["summary"]["total_messages"] == 1
    assert b["summary"]["total_tokens"] == 8  # only ws-b's 8-char body
    # No cross-contamination: ws-a never reports ws-b's bigger token total.
    assert a["summary"]["total_tokens"] != b["summary"]["total_tokens"]


# --------------------------------------------------------------------------- #
# S9 / AC8 / BR10 - top-8 + others, in agents[] AND each bucket
# --------------------------------------------------------------------------- #
def test_top_8_plus_others(deps):
    ws = "ws-many"
    setup_workspace(deps, ws)
    agents = [f"ag{i:02d}" for i in range(10)]
    setup_agents(deps, *agents)
    # agent i sends one message with body length (i+1) -> token count i+1, so the
    # ranking by tokens is ag09 (10) ... ag00 (1); top-8 are ag09..ag02.
    for i, a in enumerate(agents):
        seed_message(deps, ws=ws, agent=a, body="x" * (i + 1), at_epoch=NOW_EPOCH - 600)

    data = make_service(deps).analytics(workspace_id=ws, window="24h")

    assert len(data["agents"]) == 8
    top_ids = [a["agent_id"] for a in data["agents"]]
    assert top_ids[0] == "ag09" and "ag00" not in top_ids and "ag01" not in top_ids
    assert data["others"] is not None
    assert data["others"]["agent_count"] == 2  # ag00 + ag01
    assert data["others"]["count"] == 2
    assert data["others"]["tokens"] == 1 + 2  # bodies of length 1 and 2

    # The current bucket's by_agent has at most 9 keys (8 agents + 'others').
    current = data["buckets"][-1]
    assert len(current["by_agent"]) == 9
    assert "others" in current["by_agent"]
    assert current["by_agent"]["others"]["count"] == 2
    assert current["by_agent"]["others"]["tokens"] == 3


# --------------------------------------------------------------------------- #
# bounded truncation (FR9)
# --------------------------------------------------------------------------- #
def test_truncation_flag(deps):
    ws = "ws-trunc"
    setup_workspace(deps, ws)
    setup_agents(deps, "A")
    for _ in range(5):
        seed_message(deps, ws=ws, agent="A", body="hi", at_epoch=NOW_EPOCH - 600)

    data = make_service(deps, max_messages=3).analytics(workspace_id=ws, window="24h")
    assert data["truncated"] is True
    assert data["scanned_messages"] == 3  # capped at max_messages


# --------------------------------------------------------------------------- #
# empty workspace - zeros, never 404/None-shaped
# --------------------------------------------------------------------------- #
def test_empty_workspace(deps):
    ws = "ws-empty"
    setup_workspace(deps, ws)
    data = make_service(deps).analytics(workspace_id=ws, window="24h")
    assert data["scanned_messages"] == 0
    assert data["truncated"] is False
    assert len(data["buckets"]) == 24
    assert all(b["total_count"] == 0 and b["by_agent"] == {} for b in data["buckets"])
    assert data["summary"]["total_messages"] == 0
    assert data["summary"]["total_tokens"] == 0
    assert data["summary"]["avg_tokens_per_msg"] == 0
    assert data["summary"]["p95_tokens"] == 0
    assert data["summary"]["peak_bucket_start"] is None
    assert data["agents"] == []
    assert data["others"] is None


def test_unknown_window_raises(deps):
    with pytest.raises(ValueError):
        make_service(deps).analytics(workspace_id="ws", window="99h")
