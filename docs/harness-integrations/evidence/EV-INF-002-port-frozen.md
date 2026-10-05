# EV-INF-002 — Shared harness transport port frozen (Phase 2)

Captured: 2026-09-20 09:44 -03
Commits: `b0db60b` (port), `df40c10` (capability-lie fix)

## Deliverable

- `src/okto_nexus/domain/harness.py` — stdlib-only domain types.
- `src/okto_nexus/application/ports.py` — `HarnessConnector`, `HarnessSubscriberRegistry`.
- `tests/test_harness_domain.py` — 25 tests, one construction case per real protocol shape.

## The design decision that makes four protocols coexist

`HarnessConnector.send()` returns NO correlated reply for ANY transport. Replies always arrive
later as a `HarnessEvent` via `events()` / the subscriber registry. This is what lets
fire-and-forget `cc-socks` satisfy the identical signature as full-duplex Codex, without the
port pretending the two are the same.

Capability flags model ONLY what changes supervisor control flow:

    send_only                        is a reply ever awaited?
    steer_timing                     IMMEDIATE | NEXT_TURN_BOUNDARY | None (unsupported)
    interrupt_requires_settle_wait   Pi's abort -> settle -> reprompt ordering
    multiplexes_sessions             Codex: one connection, many sessions
    observes_session_end             can an ENDED transition ever be produced?

`native_event` is carried verbatim and never branched on, so D2 holds (no native vocabulary in
the domain) while traceability survives.

## Mapping

| Harness | send_only | steer_timing | settle wait | multiplexes | observes end |
|---|---|---|---|---|---|
| Pi | False | NEXT_TURN_BOUNDARY | True | False | yes |
| Codex | False | IMMEDIATE | False | True | yes |
| Claude Code D7a | False | IMMEDIATE | False | False | True |
| Claude Code D7b | True | None | n/a | False | False |

## Finding: cc-socks fits only degenerately

D7b satisfies the port only in the degenerate case where every control-flow capability takes its
"cannot" value: no minted identity (`session_id` is OBSERVED from the peer pid/hash, not created
by Nexus), no observable end (`observes_session_end=False`, so its session can legally go
STARTING -> RUNNING and then simply be abandoned — there is no producer for ENDED), no steering,
and no interrupt semantics.

An earlier draft forced D7b to declare `steer_timing=NEXT_TURN_BOUNDARY` as if it were a Pi-like
buffered-steer transport. **That was a capability lie** — a supervisor could not have
distinguished a real buffered-steer session from a cannot-steer-at-all one. Fixed by making
`steer_timing` nullable.

**Constraint recorded for future work:** if a fifth harness appears missing a DIFFERENT subset
of these capabilities, add a second, narrower port for attach-only transports. Do NOT bolt a
sixth boolean onto this one. This port already carries one connector that is mostly False/None.

## Verification

```
$ uv run python -m pytest -q tests/test_import_boundary.py
3 passed

$ uv run python -m pytest -q tests/test_harness_domain.py
25 passed

$ uv run python -m pytest -q          # full suite
1638 passed, 2 skipped

$ uv run ruff check .
All checks passed!
```

Regression check vs EV-INF-001 (1613 passed, 2 skipped): +25, exactly the new domain tests.
ZERO regressions.

No connector, adapter, migration or HTTP/MCP wiring was touched — the Phase 2 boundary held.
