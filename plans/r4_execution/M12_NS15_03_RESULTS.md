# NS15.03 canonical result materialization — October 1, 2026

Schema 095 adds `execution_results`, keyed by the canonical operation identity
and referencing the exact terminal event in the authenticated R4 stream. It
does not fabricate legacy harness sessions/events or alter their foreign keys.
Existing history is preserved by additive migration.

The event ingress materializes only newly contiguous events in the same
transaction as event persistence and watermark advancement. Gaps defer output;
replay cannot append it twice. Text snapshots replace earlier output, deltas and
terminal redaction tails append, and materialization is bounded to 1 MiB of UTF-8.
Truncation is explicit. Once terminal, later observations cannot replace output.

The existing authorized `GET /v1/runtime/operations/{id}` view includes `result`
when a correlated turn has a contiguous terminal event. The result identifies
its session, stream epoch and terminal sequence. A receipt alone does not create
output. Its delivery outcome is a technical fact, not handoff completion.

Tests cover the public embedded/Core/HTTP path, snapshots/deltas, replay, gaps,
transaction rollback, UTF-8 bounds and migration of prior R4 history. Installed
campaigns also cover event ingress authority, conversation/handoff delivery and
legacy governed work. Native readiness/providers remain fixture-local.
The installed campaigns passed **73 distinct product tests and 3 architecture
checks**; see `test_runs_20261001_ns15_03_results.json` and the `ns15-03-results-*`
logs/manifests. The HTTP schema also describes the optional result field.

This is the capture/read part of result integration. Conversation publication,
canonical structured work decisions, result artifacts/retention, domain event
publication, combined claim competition, cross-protocol fallback and native
loader removal remain pending. Normative TR4-06-05/TR4-15-03 and release gates
remain open. No handoff is completed by text or a terminal event.
