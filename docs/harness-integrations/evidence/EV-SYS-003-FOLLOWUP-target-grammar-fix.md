# EV-SYS-003-FOLLOWUP — closing the target-grammar gap (SYS-03 / UAT-05)

Captured: 2026-09-20. Branch `feature/harness-integrations`, starting HEAD `3963bd1`. This file
documents the BUILD task ("make the target grammar actually reach harnesses"), not a re-audit —
it assumes `EV-SYS-003-target-grammar-gap.md` and `EV-UAT-05-target-grammar-asymmetry.md`'s
findings as its reproduction baseline rather than re-deriving them (both were correct, real
findings at the commit they were captured against).

**Verdict: FIXED.** The existing target grammar (`direct`/`capability`/`role`/`tag`, resolved by
`message_create` per ADR 0001) now reaches a live harness session. Proven at two levels: unit
tests against a fake connector (failing-first, then passing), and a live re-run of the exact
SYS-03 check against a real running hub with a real `pi` child, reversing the original result.

## Design

`domain/harness.py` and the `HarnessConnector`/`HarnessSubscriberRegistry` Protocols in
`application/ports.py` are FROZEN for this task and were not touched. Everything below is either a
NEW port (explicitly permitted) or a change to non-frozen application/adapter code.

**D1 (no polling) — the honest answer, stated plainly first.** There is no existing push
primitive on the ordinary message inbox: `application/inbox.py`/`application/messages.py` have no
listener/callback/subscribe hook anywhere (`grep -n "listener\|subscribe\|callback\|on_delivery\|hook"`
over both files returns zero hits), and the only notification primitive in the whole codebase is
`SleepPollWaiter`, which the harness path must never touch (D1; `EV-SYS-006`'s structural
import-closure test enforces this). Piggybacking on the existing `EventEmitter`/`message.created`
event was considered and rejected: `emit` is a SQLite write inside the SAME write `uow` as the
delivery row, so consuming it as a signal would mean polling the event table afterward — exactly
what D1 forbids. The smallest honest mechanism is therefore a NEW port,
`InboxDeliveryNotifier` (`application/ports.py`), structurally identical to the existing
`HarnessSubscriberRegistry` (`subscribe`/`unsubscribe`/`publish`, synchronous, in-process, no
queue, no storage) but keyed by recipient `agent_id` instead of harness `session_id`. Its concrete
adapter, `InMemoryInboxDeliveryNotifier` (`adapters/outbound/inbox_notifier.py`), is a near-exact
copy of `InMemoryHarnessSubscriberRegistry`'s lock-snapshot-then-call-outside-the-lock shape and
its one-broken-subscriber-never-breaks-another isolation.

**Reuses the existing inbox machinery — no parallel delivery path.** `MessageService.create_message`
still creates exactly the delivery rows it always did (ADR 0001, unchanged). The ONLY addition is
one best-effort call, `_maybe_notify_inbox_subscribers`, made AFTER the write `uow` commits (mirrors
the existing `_maybe_generate_embedding` best-effort-after-commit pattern already in that method),
which publishes the already-assembled response `data` to the notifier for each recipient. A
subscriber's absence, or a subscriber raising, never touches the delivery rows already committed —
they are durable before this call ever runs.

**`HarnessSupervisor.open` subscribes; `_claim_for_reap` unsubscribes.** On a successful `open`
(on-demand AND boot-declared — `open_declared` converges on `open`, D8), the supervisor subscribes
a callback for the new session's `owning_agent_id`. `_claim_for_reap` is the single place anything
leaves the live registry (per its own pre-existing docstring), so it is also the single place the
subscription is torn down — a reaped/closed session stops receiving forwards immediately.

**The forward reuses `HarnessSupervisor.send` itself — not a bespoke gate.** The callback
(`_on_inbox_delivery`) calls `self.send(session_id, "send_turn", payload)`, the exact method the
existing direct-`session_id` HTTP (`POST /harness/sessions/{id}/send`) and MCP (`harness_send`)
call sites already use. This means the forward inherits, for free: the live-session check
(`_require_live`), and the EXISTING capability guard (`_require_verb_allowed`) that already
rejects `steer`/`interrupt` against a `send_only` connector (D7b/cc-socks) and rejects `steer`
against a connector with `steer_timing=None`. There is nothing bespoke to independently get
wrong — a regression in that guard breaks both the pre-existing direct-addressing path and this
new forward path identically, and `test_send_only_connector_rejects_everything_but_send_turn`
(pre-existing, `test_harness_supervisor.py`) already covers it directly; this task's own
`test_harness_target_grammar.py::test_send_only_connector_still_rejects_steer_directly` and
`::test_forward_to_a_send_only_connector_only_ever_issues_send_turn` prove the forward path never
attempts anything else and inherits that guard.

**Bounded (D8).** The forward runs inside `_bounded_call` (the same `Thread.join(timeout)`
non-polling pattern `open`/`close` already use), `DEFAULT_FORWARD_TIMEOUT_SECONDS = 10.0`, because
it executes on the CALLING thread of whatever fired `message_create` (an MCP tool call, an HTTP
request) — a connector's own `send` can genuinely block on a transport write/ack (pi's
`_send_turn` awaits a reply up to its own command timeout), and that caller must never wedge past
a bound.

**Ack/consume semantics: hand-off, never consumption.** `HarnessConnector.send` is fire-and-forget
by the FROZEN port's own contract ("Never blocks for a reply… any reply is delivered later as a
HarnessEvent"), so there is no delivery-confirmation event this forward could ever ack on — making
ack-on-delivery-confirmation not implementable, and ack-on-handoff wrong (it would mark a message
consumed that the harness may never have actually processed, the exact silent loss the task
forbids). The decision: **the ordinary inbox delivery row is never mutated by the forward,
succeeding or failing.** It is created exactly as ADR 0001 always created it, stays `unread`
regardless of what the forward does, and is claimable through the ordinary `inbox_pull`/`inbox_ack`
path independent of whether anything is even subscribed. Proven directly:
`test_delivery_row_is_unaffected_by_forward_outcome_either_way` asserts the delivery row's
`status` column is `"unread"` after a successful forward.

**Payload key asymmetry.** The three full-duplex connectors read DIFFERENT payload keys for
`send_turn`: `pi`/`codex` read `payload["text"]`; `claude_code` (stream substrate) reads
`payload["content"]`. Rather than switch on `harness_kind`, the forward sets BOTH keys
(`{"text": body, "content": body}`) — each connector reads only its own key via a plain `.get(...)`,
so the extra key is inert, and this stays correct without updating this method if a future
connector picks a key nobody else claims. Covered for both key conventions:
`test_direct_target_reaches_the_connector` (pi, `text`) and
`test_forward_to_a_send_only_connector_only_ever_issues_send_turn` (`claude_code`, `send_only`).

**Harness-to-harness feedback loop (found during design, not in the original task text) —
guarded and tested.** D10 already delivers a harness's own notable event (`turn_completed`) as an
ordinary message FROM its `owning_agent_id`. Without a guard, two live harnesses each
`notify_target`-ing the other's registered agent would ping-pong forever: A's turn completes →
message → forwarded into B as a turn → B's turn completes → message → forwarded into A → … `SYS-09`
already proves multiple harnesses live concurrently in one workspace, so this is reachable, not
theoretical. Guard: `_on_inbox_delivery` never forwards a message whose `from_agent_id` is itself a
CURRENTLY-LIVE harness session's `owning_agent_id` (any one, not just the receiving session's own —
`_live_owning_agent_ids()`, read fresh under the existing lock on every delivery). This is strictly
broader than the trivial self-addressed case (a `notify_target` pointed at the harness's own
`agent_id`) — `direct` targets do NOT exclude the sender at the routing layer the way group
targets do (`MessageService._resolve_recipients`'s own docstring: "you never inbox your own
broadcast" applies only to non-directed targets). Both cases are tested:
`test_harness_to_harness_notable_messages_do_not_cascade` (two live sessions, mutual
`notify_target`, zero forwards either direction) and `test_self_addressed_direct_message_does_not_loop`.

Deliberate scope boundary, disclosed rather than silently assumed away: this guard means a
message genuinely SENT BY a live harness's own agent is never forwarded into any live harness,
even when that is what an operator might want (intentional multi-harness relaying). An operator
wanting that can still use direct `session_id` addressing (`harness_send`), which this guard does
not touch at all.

## Files changed

- `src/okto_nexus/application/ports.py` — new `InboxDeliveryNotifier` Protocol (NOT one of the
  two frozen ports).
- `src/okto_nexus/adapters/outbound/inbox_notifier.py` — new file, `InMemoryInboxDeliveryNotifier`.
- `src/okto_nexus/application/messages.py` — optional `inbox_notifier` constructor param;
  `_maybe_notify_inbox_subscribers`, called after `create_message`'s write `uow` commits.
- `src/okto_nexus/application/harness_supervisor.py` — optional `inbox_notifier` constructor
  param; `_LiveSession.inbox_subscription` field; subscribe in `open`, unsubscribe in
  `_claim_for_reap`; `_on_inbox_delivery` (the forwarding callback) and `_live_owning_agent_ids`
  (the cascade guard); `DEFAULT_FORWARD_TIMEOUT_SECONDS`.
- `src/okto_nexus/adapters/inbound/mcp/tools/messages.py` — composition root: wires/caches ONE
  process-wide `InMemoryInboxDeliveryNotifier` on `deps.inbox_delivery_notifier`, passes it into
  `MessageService`.
- `src/okto_nexus/adapters/inbound/mcp/tools/harness.py` — composition root: passes the SAME
  `deps.inbox_delivery_notifier` into `HarnessSupervisor`. Also: `_P_HARNESS_AGENT_ID`'s
  docstring, which (correctly, at the time) disclosed that the target grammar could NOT yet reach
  a harness (a same-run sibling agent's honest UAT-07 fix), is updated to state the NEW true,
  qualified behaviour (reaches a live session; best-effort/hand-off; `harness_send` remains the
  guaranteed-delivery, session_id-addressed alternative) — leaving the old disclosure in place
  after this fix landed would itself become exactly the shipped-false-claim defect UAT-07 found.
- `tests/test_harness_tools.py` — the pre-existing test that locked in the (correct, at the time)
  pre-fix docstring contract (`test_harness_open_agent_id_description_does_not_promise_target_
  grammar_routing`) is renamed and rewritten to assert the new, fixed docstring contract
  (`test_harness_open_agent_id_description_documents_the_sys03_fix`) — the old assertion is now
  testing an obsolete requirement, not a live invariant. This is a sibling agent's file/test
  (the "surface" task's own H-2 proof artifact); the rewritten test's docstring cross-references
  this evidence file by name, and the `_P_HARNESS_AGENT_ID` edit site in `tools/harness.py`
  carries a matching one-line pointer, so the supersession is on the record at both ends, not
  only here.

**Disclosed, not silently left stale:** `surface_metrics.py`'s `"harness_backend_h1_h2": 1680`
ledger entry records the H-2 docstring rewrite's measured char delta on the live server. This
fix's `_P_HARNESS_AGENT_ID` rewrite (on top of H-2's own) changes that same docstring's resident
size again, so `1680` no longer matches the tree. `surface_metrics.py` was not touched — remeasuring
it belongs to whoever owns that ledger/the deferred `SURFACE_REVISION` bump (see that file's own
"Deliberately NOT paired with a SURFACE_REVISION bump" note), not this task. `test_surface_
metrics.py` was checked directly and asserts nothing that pins this specific value against the
live server, so this does not fail any test — it is a known, disclosed undercount for the next
surface-accounting pass to pick up.
- `docs/harness-integrations/evidence/EV-SYS-003-target-grammar-gap.md` and
  `EV-UAT-05-target-grammar-asymmetry.md` — addenda pointing forward to this file; original
  verdicts left untouched (they were correct at the commit they were captured against).
- `tests/test_harness_target_grammar.py` — new file, this fix's own test suite (below).

## Failing-first evidence

`tests/test_harness_target_grammar.py` was written and run against the CURRENT code (before
`ports.py`/`inbox_notifier.py`/`messages.py`/`harness_supervisor.py` were touched), using ONLY
today's public API — no new import, so a failure is a real behavioural gap, never an `ImportError`
for the wrong reason.

First clean capture (after fixing one test-authoring bug of its own —
`test_forward_failure_does_not_wedge_the_session` originally called `supervisor.send()` directly a
second time against a connector that unconditionally raises on every call, which is not what that
test intends to prove; fixed to send a second, independent `message_create` instead):

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_target_grammar.py
FFF..FF..                                                                [100%]
...
FAILED tests/test_harness_target_grammar.py::test_direct_target_reaches_the_connector
FAILED tests/test_harness_target_grammar.py::test_capability_target_reaches_the_connector
FAILED tests/test_harness_target_grammar.py::test_tag_target_reaches_the_connector
FAILED tests/test_harness_target_grammar.py::test_forward_to_a_send_only_connector_only_ever_issues_send_turn
FAILED tests/test_harness_target_grammar.py::test_delivery_row_is_unaffected_by_forward_outcome_either_way
5 failed, 4 passed in 21.00s
```

Each of the 4 behavioural failures (`direct`, `capability`, `send_only`-forward, delivery-row-ack)
failed on `assert wait_until(lambda: len(_send_turn_commands(connector)) == 1)` — a clean,
real-behaviour assertion failure: the fake connector received zero commands, reproducing SYS-03's
finding at the application layer (`message_create` reports success; the connector never sees it).
The 4 tests that passed pre-fix did so for the expected reason: the two no-cascade tests trivially
pass with nothing forwarding at all yet, `test_forward_failure_does_not_wedge_the_session` is
regression coverage for a NEW isolation property (not a defect reproduction — nothing to wedge
yet), and `test_send_only_connector_still_rejects_steer_directly` exercises the PRE-EXISTING
`HarnessSupervisor.send` capability guard directly, unrelated to this fix.

**Disclosed, not glossed over:** `test_tag_target_reaches_the_connector` failed above, but not
cleanly — the failure shown was `TypeError: SqliteAgentRepo.upsert() got an unexpected keyword
argument 'tags'`, a bug in the TEST's own setup helper (the wrong repo method), not a reproduction
of the SYS-03 gap. That bug (and a second one — 'tag' targeting additionally requires WORKSPACE
PRESENCE, `domain.inbox.requires_workspace_audience`, which the test also initially omitted) were
both found and fixed AFTER the feature implementation already existed, so `tag`'s pre-fix failure
was never captured in clean isolation the way `direct`/`capability` were. This is disclosed rather
than silently presented as equivalent evidence: `tag`'s post-fix PASS is real (it goes through the
identical `_on_inbox_delivery`/`_maybe_notify_inbox_subscribers` code path already proven
end-to-end by the `direct` and `capability` tests, so there is no reason to expect it to behave
differently), but its specific pre-fix failure is inferred from that shared code path, not
independently observed.

Also added post-fix (not part of the failing-first capture; `role` resolves against the global
registry exactly like `capability` and needs no new machinery, but the "direct/capability/role/tag"
claim in this file's own verdict line otherwise names one strategy no test covers):
`test_role_target_reaches_the_connector`.

## Post-fix: full new suite green

```
$ timeout 120 uv run python -m pytest -q tests/test_harness_target_grammar.py tests/test_harness_tools.py
....................................                                      [100%]
36 passed in 1.74s
```

`test_harness_target_grammar.py` alone: 11 tests (the 9 captured failing-first above, plus
`test_role_target_reaches_the_connector` and
`test_real_composition_root_wires_the_shared_notifier`, which exercises
the REAL production composition root — `bootstrap()` + `tools/messages.py::build_service` +
`tools/harness.py::build_service` — rather than this file's own hand-wired `wired()` helper,
proving the two composition roots actually share ONE notifier instance in production wiring, not
only in a test double).

## Live re-run of SYS-03 (real hub, real pi child, real MCP call)

Mirrors `EV-SYS-003-target-grammar-gap.md`'s own methodology exactly (real `okto-nexus serve`
subprocess bound to a real socket, a real `nxs_` agent key from `POST /agents`, the real
`message_create`/`harness_open`/`harness_event_list` MCP tools over the REAL Streamable-HTTP
`/mcp` mount via `mcp.ClientSession` — never a `TestClient`), but this time the connector's own
event log (`harness_event_list` — durable, per-session, sequenced; this IS the "wire trace" this
task asks to show gaining bytes, since `pi.py` writes no separate raw trace file of its own) is
checked before/after instead of the original driver's raw socket line-count.

Hardware, per this task's rules: pi's own `~/.pi/agent/settings.json` `defaultProvider` is
`local-mac` (resolves to the off-limits `.222` box) — overridden via the NEW `backend` param
(landed by a sibling "surface" agent's task this same run) to `zai/glm-5.3`, which `~/.pi/agent
/settings.json`'s own `enabledModels` already lists as pre-configured. `okto-nexus serve` was run
from an isolated scratchpad `--home`/`--project-root`, on an ephemeral port (8391), bounded by
`timeout 280`.

```
$ timeout 15 curl -s -X POST http://127.0.0.1:8391/api/v1/agents -d '{"agent_id":"sys03_probe_live"}'
{"ok":true,"data":{"agent_id":"sys03_probe_live", ..., "api_key":"nxs_aa0e2c4f..."}}

$ timeout 120 uv run python sys03_live_rerun.py "nxs_aa0e2c4f..." "<scratch>/sys03-proj"

=== harness_open (pi, backend=zai/glm-5.3) ===
harness_open -> {
  "session_id": "hsess_323656deb61f40ad8649ec88a21225b7",
  "owning_agent_id": "sys03_pi_agent_live",
  "status": "RUNNING",
  "backend": {"explicit": true, "applied": {"provider": "zai", "model": "glm-5.3"},
              "note": "backend override applied exactly as given."}
}

=== harness_event_list BEFORE ===
BEFORE_EVENT_COUNT: 7   (extension_ui_request / statusline bootstrap chatter)

=== message_create via the EXISTING target grammar (direct) ===
message_create -> {
  "from_agent_id": "sys03_probe_live",
  "target": {"strategy": "direct", "agent_id": "sys03_pi_agent_live"},
  "recipients": ["sys03_pi_agent_live"],
  "delivered_count": 1
}

=== waiting for the pi child to actually answer ===
AFTER_EVENT_COUNT: 11
NEW_WIRE_ACTIVITY: True
NEW_EVENT_KINDS: ['tool_activity', 'turn_started', 'tool_activity', 'tool_activity']
 - tool_activity native_event= agent_start
 - turn_started    native_event= turn_start
 - tool_activity   native_event= message_start
 - tool_activity   native_event= message_end

=== harness_close ===
harness_close -> {"status": "ENDED"}
```

**Reversal of the original finding, real and unambiguous.** The message was addressed by a
DIFFERENT sender (`sys03_probe_live`) at the harness's registered agent
(`sys03_pi_agent_live`) purely through `message_create`'s `direct` target — the exact call shape
`EV-SYS-003` used, which previously left the pi child's wire trace byte-identical (17 lines before,
17 after). This time: 7 events before, 11 after, and the 4 new events are precisely what a real
NEW turn looks like from the outside (`agent_start` → `turn_started`/`turn_start` →
`message_start` → `message_end`) — `zai/glm-5.3` genuinely received and processed "reply with the
single word: ok" as a consequence of the target-grammar `message_create` call, with no direct
`session_id`-addressed call (`harness_send`) made anywhere in this script. `sys03_live_rerun.py`
is scratchpad-only per the EV-CX-001/EV-PI-INT-001/EV-SYS-003 convention; this inlined output is
the committed artifact.

Note on the sender: a self-addressed direct message (`from_agent_id == target agent_id`) would
correctly be SKIPPED by the harness-to-harness cascade guard above — the script deliberately
registers and connects as a separate `sys03_probe_live` identity to exercise the genuine
third-party-addressing case, not the guard's own degenerate case (which
`test_self_addressed_direct_message_does_not_loop` already covers).

## Full suite + lint

```
$ timeout 900 uv run python -m pytest -q
...
1857 passed, 4 skipped, 2 warnings in 151.68s (0:02:31)

$ timeout 300 uv run ruff check .
All checks passed!
```

Measured on a tree containing CONCURRENT sibling-agent edits (this same run, same branch, per the
task's own "other agents work in this tree concurrently" rule) — this number is not attributable
to this task's diff alone. This task's own contribution: `tests/test_harness_target_grammar.py`
(11 new tests) and one rewritten test in `tests/test_harness_tools.py` (see "Files changed"
above); no other test file was touched by this task. The task's stated REG-01 reference point was
"2 failed, 1822 passed, 4 skipped" before Phase 5, with the 2 failures named as a sibling codex
agent's own deliberate defect-witness tests for that same run. Arithmetic check: 1822 + 11 (this
task) = 1833; the observed 1857 is 24 higher, all from OTHER sibling agents' own new tests landing
in the same tree during this run - not reconciled further here, since attributing rows outside
this task's own diff is exactly the over-claiming EV-INDEX.md's own methodology note warns
against. What this run DOES support directly: `0 failed` — REG-01's "zero pre-existing failures"
bar is met on this measurement, and none of the 0 failures are this task's own regression.
