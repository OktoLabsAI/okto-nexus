"""Workspace message-distribution analytics (read-time, hexagonal).

Aggregates a SINGLE workspace's messages over a time window into a per-bucket,
per-agent series with TWO metrics - volume (message count) and size (TOKENS via
the :class:`Tokenizer` port) - plus summary stats and a bounded top-agent
breakdown. This is the application service behind ``GET /workspaces/{id}/analytics``.

Pure application layer: depends only on ports (``ConnectionFactory`` for a
READ-only unit of work, ``ObservabilityQueries``, ``Tokenizer``, ``Clock``).
No SQL, no HTTP, no tiktoken import here. Token counting happens in Python over
a BOUNDED window fetch (the repo never tokenises; ``length()`` != tokens), at
READ time, behind the port - the message write path is never touched (BR7).

Design locks honoured: size = TOKENS not bytes (BR1); breakdown by SENDER
``from_agent_id`` (BR2); source = ``messages`` table (BR3); strict workspace
isolation (BR4); bucket DERIVED from the window (BR8); bounded top-8 + others in
both ``agents`` and every bucket's ``by_agent`` (BR10).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from ..domain.base import iso_to_epoch
from .ports import Clock, ConnectionFactory, ObservabilityQueries, Tokenizer

#: window -> (total span seconds, bucket seconds). The bucket is DERIVED from the
#: window (BR8), never configured by hand: 24h->1h, 7d->6h, 30d->1d. span/bucket
#: is exactly 24 / 28 / 30 buckets respectively.
WINDOWS: dict[str, tuple[int, int]] = {
    "24h": (86_400, 3_600),
    "7d": (604_800, 21_600),
    "30d": (2_592_000, 86_400),
}

#: The default window when the caller does not specify one.
DEFAULT_WINDOW = "24h"

#: Defensive ceiling (FR9): tokenisation reads at most this many of the MOST
#: RECENT messages in the window. Beyond it the response is flagged
#: ``truncated`` with ``scanned_messages`` so the operator knows it is capped.
ANALYTICS_MAX_MESSAGES = 50_000

#: Per-agent breakdown cap (BR10): the top-N agents by tokens; everyone else
#: folds into an ``others`` aggregate - in ``agents`` AND in every bucket's
#: ``by_agent`` (so a bucket carries at most TOP_AGENTS + 1 keys).
TOP_AGENTS = 8
OTHERS_KEY = "others"


def is_valid_window(window: str | None) -> bool:
    """Whether ``window`` is one of the supported values (route validation)."""
    return window in WINDOWS


def _epoch_to_iso(epoch: float) -> str:
    """Render an aligned bucket-start epoch as a canonical fixed-width ISO string.

    Microsecond precision (``...000000Z``) so the value is the SAME fixed-width
    UTC grammar as stored ``created_at`` timestamps - the ``created_at >=
    since_iso`` window filter is a lexicographic SQL string compare, and a
    seconds-precision boundary (``...00Z``) would order WRONG against a
    microsecond timestamp (``.`` < ``Z``), silently dropping sub-second rows.
    """
    return (
        datetime.fromtimestamp(epoch, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def p95_nearest_rank(values: list[int]) -> int:
    """95th percentile by the NEAREST-RANK method (deterministic, no interp).

    Sort ascending; the p95 is the value at 1-based index ``ceil(0.95 * N)`` -
    i.e. the smallest value such that at least 95% of the samples are <= it.
    ``N == 0`` -> 0. Used identically for the summary and per-agent p95.
    """
    if not values:
        return 0
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered))  # 1-based, always >= 1
    return ordered[rank - 1]


class WorkspaceAnalyticsService:
    """Compute the message-distribution analytics for one workspace + window."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        queries: ObservabilityQueries,
        tokenizer: Tokenizer,
        clock: Clock,
        max_messages: int = ANALYTICS_MAX_MESSAGES,
    ) -> None:
        self._cf = connection_factory
        self._q = queries
        self._tokenizer = tokenizer
        self._clock = clock
        self._max_messages = int(max_messages)

    def analytics(self, *, workspace_id: str, window: str = DEFAULT_WINDOW) -> dict[str, Any]:
        """Return the analytics payload (the ``data`` of the canonical envelope).

        ``window`` MUST be one of :data:`WINDOWS` (the route validates it and
        raises ``INVALID_WINDOW`` first); an unknown value here is a wiring bug,
        so we fail loud with ``ValueError``.
        """
        if window not in WINDOWS:
            raise ValueError(f"unknown analytics window: {window!r}")
        span_seconds, bucket_seconds = WINDOWS[window]
        n_buckets = span_seconds // bucket_seconds

        # Bucket grid: exactly n_buckets aligned buckets ending at the bucket that
        # CONTAINS now (floor-aligned epoch), covering the most recent window.
        now_epoch = self._clock.now_epoch()
        last_start = (int(now_epoch) // bucket_seconds) * bucket_seconds
        first_start = last_start - (n_buckets - 1) * bucket_seconds
        bucket_starts = [first_start + i * bucket_seconds for i in range(n_buckets)]
        since_iso = _epoch_to_iso(first_start)

        with self._cf.unit_of_work(write=False) as uow:
            total = self._q.workspace_message_count(
                uow, workspace_id=workspace_id, since_iso=since_iso
            )
            rows = self._q.workspace_message_rows(
                uow,
                workspace_id=workspace_id,
                since_iso=since_iso,
                limit=self._max_messages,
            )

        truncated = total > self._max_messages
        scanned = len(rows)

        # Per-(bucket, agent) and per-agent accumulators. Token counts per message
        # are kept (overall + per agent) to compute nearest-rank p95.
        per_bucket: dict[int, dict[str, dict[str, int]]] = {
            start: {} for start in bucket_starts
        }
        per_agent: dict[str, dict[str, Any]] = {}
        all_tokens: list[int] = []

        for row in rows:
            agent = row["from_agent_id"]
            tokens = self._tokenizer.count_for_message(
                row["message_id"], row["body"]
            )
            all_tokens.append(tokens)

            epoch = iso_to_epoch(row["created_at"])
            bstart = (int(epoch) // bucket_seconds) * bucket_seconds
            # Defensive: a row exactly on the lower edge could floor below
            # first_start under clock skew; clamp into the grid.
            if bstart < first_start:
                bstart = first_start
            elif bstart > last_start:
                bstart = last_start
            cell = per_bucket[bstart].setdefault(agent, {"count": 0, "tokens": 0})
            cell["count"] += 1
            cell["tokens"] += tokens

            ag = per_agent.setdefault(
                agent, {"count": 0, "tokens": 0, "token_list": []}
            )
            ag["count"] += 1
            ag["tokens"] += tokens
            ag["token_list"].append(tokens)

        # Rank agents by total tokens (desc), tie-break by id for determinism.
        ranked = sorted(
            per_agent.items(), key=lambda kv: (-kv[1]["tokens"], kv[0])
        )
        top_ids = {agent for agent, _ in ranked[:TOP_AGENTS]}

        agents_out: list[dict[str, Any]] = []
        for agent, data in ranked[:TOP_AGENTS]:
            count = data["count"]
            tokens = data["tokens"]
            agents_out.append(
                {
                    "agent_id": agent,
                    "count": count,
                    "tokens": tokens,
                    "avg_tokens": (tokens / count) if count else 0,
                    "p95_tokens": p95_nearest_rank(data["token_list"]),
                }
            )

        others_rest = ranked[TOP_AGENTS:]
        others_out: dict[str, int] | None = None
        if others_rest:
            others_out = {
                "agent_count": len(others_rest),
                "count": sum(d["count"] for _, d in others_rest),
                "tokens": sum(d["tokens"] for _, d in others_rest),
            }

        # Assemble the per-bucket series, collapsing non-top agents into 'others'.
        buckets_out: list[dict[str, Any]] = []
        peak_start: int | None = None
        peak_count = -1
        for start in bucket_starts:
            bagents = per_bucket[start]
            by_agent: dict[str, dict[str, int]] = {}
            others_cell = {"count": 0, "tokens": 0}
            total_count = 0
            total_tokens = 0
            for agent, cell in bagents.items():
                total_count += cell["count"]
                total_tokens += cell["tokens"]
                if agent in top_ids:
                    by_agent[agent] = {
                        "count": cell["count"],
                        "tokens": cell["tokens"],
                    }
                else:
                    others_cell["count"] += cell["count"]
                    others_cell["tokens"] += cell["tokens"]
            if others_cell["count"] or others_cell["tokens"]:
                by_agent[OTHERS_KEY] = others_cell
            buckets_out.append(
                {
                    "bucket_start": _epoch_to_iso(start),
                    "total_count": total_count,
                    "total_tokens": total_tokens,
                    "by_agent": by_agent,
                }
            )
            if total_count > peak_count:
                peak_count = total_count
                peak_start = start

        total_messages = scanned
        total_tokens_sum = sum(all_tokens)
        summary = {
            "total_messages": total_messages,
            "total_tokens": total_tokens_sum,
            "avg_tokens_per_msg": (
                total_tokens_sum / total_messages if total_messages else 0
            ),
            "p95_tokens": p95_nearest_rank(all_tokens),
            # Peak bucket is the highest-VOLUME bucket; None only when there are
            # no messages at all (every bucket is zero).
            "peak_bucket_start": (
                _epoch_to_iso(peak_start)
                if peak_start is not None and peak_count > 0
                else None
            ),
        }

        return {
            "window": window,
            "bucket_seconds": bucket_seconds,
            "truncated": truncated,
            "scanned_messages": scanned,
            "buckets": buckets_out,
            "summary": summary,
            "agents": agents_out,
            "others": others_out,
        }
