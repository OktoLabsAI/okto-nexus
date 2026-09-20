# EV-REV-003 — Pi connector remediation, adversarial recheck

Captured: 2026-09-20 11:17 -03
Verdict: all 5 defects CLOSED. Gates clean. One honest downgrade recorded.

## Method — empirical, not by report

The rechecker did NOT trust the remediator's prose. For C1, C2, C3 and M2 it reverted each fix
individually in the live working tree, ran the corresponding new test, confirmed it FAILED, then
restored the byte-identical original and verified with `diff`. A test that still passes against
reverted code proves nothing; all four genuinely failed.

| Defect | Verdict | Empirical evidence |
|---|---|---|
| C1 settle gate / mock ordering | CLOSED | reverting the fake to ack-first made `test_interrupt_blocks_further_sends_until_agent_settled` fail with a CONFLICT it should not raise |
| C2 events() fan-out | CLOSED | reverting to one shared Queue made consumer A hang; `assert not thread_a.is_alive()` failed |
| C3 failed start() loops forever | CLOSED | reverting `_closed_event` in start()'s except left the drainer thread never returning within 5s |
| M1 timed-out abort ack wedges gate | CLOSED | by inspection: rollback covers both `request()` failure modes |
| M2 child death not fail-fast | CLOSED | reverting `_fail_all_pending` made `interrupt()` block the full 2.0s timeout (~2.06s measured) |

## The semantic claim was checked, not accepted

The remediation concluded that because `agent_settled` precedes the abort ack, a reprompt
immediately after `interrupt()` returns is LEGITIMATELY safe — and rewrote a test that had
asserted the opposite. A remediation pass that WEAKENS an assertion is the most dangerous possible
outcome, so this was independently verified.

Confirmed correct against protocol reference section 6(b) for BOTH cases: no-tool-in-flight (2ms)
and mid-tool-call (~30ms). Settle always precedes the ack. The real danger window — a concurrent
`send_turn` arriving while `interrupt()` is still blocked on the delayed ack — is exercised by
`test_interrupt_gate_holds_during_real_race_window`, which starts a second thread mid-block and
asserts CONFLICT. Verified as a genuine concurrency test, not a happy-path decoration.

## DOWNGRADE — the generation token is COSMETIC

`_awaiting_settle_generation` (int + `itertools.count`) was reverted to a plain `_awaiting_settle`
bool across six call sites (`__init__`, `start`, `_guard_not_awaiting_settle`, `_interrupt`,
`_on_push_event`, `_on_child_exit`) and the suite re-run: **21 passed / 1 skipped, UNCHANGED**.

Because the CONFLICT guard already forbids two live generations at once, there is never a second,
different generation for the integer to disambiguate against. It changes no observable behaviour
versus a bool.

The ROOT defect — wrong gate-clear timing/ordering — IS genuinely fixed. But the identity-tracking
vocabulary is dressing, and the fix does NOT provide the cross-turn correlation its name implies.
The module's own docstring admits this ("at most one is ever outstanding... reported honestly, not
oversold"), so this is honest rather than misleading. Recorded here so no future reader mistakes
the name for the guarantee.

If pi ever gains a per-turn id on `agent_settled`, this is the place real correlation would go.

## Fake server audit beyond C1

Checked against the protocol reference, no divergence found:
- 7 unsolicited `extension_ui_request` lines on spawn — matches.
- No ready/hello event; readiness relies purely on the `get_state` response — matches.
- Steer's immediate `queue_update` vs delivery deferred to the next turn boundary — matches §5.
- Plain-turn ordering (`agent_start, turn_start, message_start/end(user), message_start(assistant),
  message_update, message_end, turn_end, agent_end, agent_settled`) — matches.

## Gates

- `failing_first_evidence_present`: YES (empirically, revert-and-fail-then-restore ×4)
- `unbounded_wait_remaining`: NO. One minor note: `self._proc.wait()` in `_read_stdout`'s `finally`
  carries no timeout, but only runs after stdout hit EOF (child already exiting), so it is not a
  genuine hang risk.
- `polling_violation`: NO. The `Queue.get(timeout=_EVENTS_POLL_S)` is a bounded liveness recheck
  for shutdown; real events satisfy `get()` immediately regardless of the timeout.
- `port_violation`: NO. `domain/harness.py` and `application/ports.py` show no changes.

## New defects introduced by the remediation

None. `_event_history` is append-only and never trimmed, but is bounded by session lifetime (one
process = one session for this connector, not a long-lived multiplexer) — a defensible design
choice, documented. Snapshot-then-subscribe in `events()` is provably atomic: the history append
and the subscriber-list mutation occur under the same `_history_lock`, so there is no
duplicate-or-missed-event gap.
