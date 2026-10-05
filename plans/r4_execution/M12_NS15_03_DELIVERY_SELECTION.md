# NS15.03 mixed delivery endpoint selection — October 1, 2026

Canonical ready sessions now participate in the existing conversation delivery
selection order: prefer ready sessions, then endpoint priority, then the stable
endpoint ID within an explicitly approved equivalence group. Equal candidates
without an equivalence group remain ambiguous. The planner and canonical
admission share one bounded binding/session selector inside the message
transaction. Multiple or unresolved canonical sessions fail before a new claim
or effect instead of causing an implicit legacy fallback.

Canonical session IDs are selection evidence only in the legacy envelope layer;
they are not written into the historical harness-session foreign key. The R4
operation mapping retains the canonical session. Legacy typed-before-write
fallback still considers legacy adapters; it cannot pass a canonical target to
the legacy constructor or borrow its execution authority. Cross-protocol
post-failure fallback remains a separate incomplete integration.

Public MCP tests cover canonical readiness over higher-priority idle legacy
endpoints, priority, approved equivalence, ambiguity rollback and an unresolved
canonical lease. Existing conversation delivery, legacy endpoint selection,
fallback and retry regressions run against the installed artifact. See
[the manifest](test_runs_20261001_ns15_03_delivery_selection.json).

No migration or Core/Connector artifact changes are included. Native peers and
readiness qualification remain fixture-local. Managed handoff delivery,
context-only observation, result/event publication, cross-protocol fallback and
native loader removal remain pending. Normative TR4-06-05/TR4-15-03 and all
release gates remain open.
