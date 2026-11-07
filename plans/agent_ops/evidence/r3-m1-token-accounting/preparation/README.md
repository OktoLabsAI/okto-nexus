# Deterministic M1 accounting preparation

This is a Temp-only prototype. No repository product, ledger, native client,
provider, credential, HTTP endpoint or service was changed or exercised.
The final qualification is **40 passed, 0 failed, 0 errors, 0 skipped** under
Python 3.13.1 `-I`, with Core 0.0.14 imported from the already
qualified isolated installation. `final-result.json` records imports, the
environment allowlist and unchanged module/test/runner hashes. The tests invoke
Core's pure `translate_native_event` with synthetic `HarnessEvent` values.
They do not prove native notification delivery in the current campaign.
The initial 39-case run and its exact inputs remain under `initial/`. Independent
review then found that a retired stream could reserve work despite refusing new
events. The final two-line guard refuses that reservation without dispatch or
state mutation. One regression covers completed old stream, explicit epoch
handover, old-stream refusal and continued admission on the active stream.

## Contract and policy

`observe` consumes the existing resolved `read_execution_events` data object:
scope, epoch, events, count, cursor, committed watermark, gap and pagination.
Raw native notifications, HTTP envelopes and unresolved artifact references are
not substitutes. `grounding.json` pins the source/schema contracts and records
existing test nodes for context; those existing suites were not rerun here.

Usage has the bundled Codex schema's `tokenUsage.total/last` counter structure.
Only cumulative `total.totalTokens` contributes, once per actual native thread,
minus an explicitly supplied pre-campaign baseline. Cached/reasoning/last fields
are not added again. Explicit same-thread epoch handover preserves high-water;
counter regression cannot reset the campaign. Replay is idempotent and conflicting
replay, cursor skips, gaps, backlog, malformed values or uncertain correlation
block new admission. Page validation is atomic.

The operational policy is a preventive stop at **100,000**, tolerance **700,000**,
one outstanding reservation, and at most **six** productive reservations across
setup_test/useful_work/continuation. Every setup consumption must participate in
the same campaign ledger; merely limiting the work wrapper to six is insufficient.
Terminal + at least one usage observation for the same turn + replay caught up
can settle a reservation under this operational policy. No usage remains unknown.
The schema does not promise a final usage update: reported totals are the known
observed minimum, not authoritative final billing. Keep observing all enrolled
threads after settlement for late notifications. Asynchronous observation and
interrupt cannot enforce a hard latency/token ceiling.

## Controller integration surface

All functions are pure reducers; returned dictionaries must be durably persisted
with the outer controller's CAS before dispatch. `checkpoint`/`restore` serialize
and checksum accounting state, detecting incomplete/accidentally modified storage;
they are not a hostile-tamper seal, storage implementation or interprocess lock.
Missing/corrupt checkpoint never silently restores a zero budget. Restoring the
same reservation never grants another dispatch. The response-loss driver remains
a separate component.

For a known enrolled stream: `reserve`, persist, dispatch/recover the same durable
intent, `bind_operation`, and replay via `observe`. Request/turn matching includes
stream namespace and operation, so identical operation IDs in another stream do
not settle it. A non-null operation in a usage event is retained and must agree
with later start/terminal events.

For `runtime.start` before session/epoch/thread creation: `prearm` takes the six
canonical binding fields already returned by `TerminalWork.binding`; persist
that reservation before the effect. Recover the same intent, then `bind_stream`
with its full twelve-field scope/epoch/native-thread identity and evidenced
baseline, `bind_operation`, and replay from sequence zero. Scope drift refuses
the binding. No further admission is allowed while the reservation is unbound.
The reducer does not discover IDs or prove that a thread was fresh; the caller
must supply those facts from the same canonical operation.

**Unresolved first-setup integration:** `connection_test.py.run` uses a private
connection-test journal and publishes a summarized test result, before a normal
execution binding exists. It does not expose its usage through the public
execution-event stream consumed here. Thus `prearm`'s known-binding prerequisite
does not currently cover that first setup:test. The controller must stop before
it until a separate explicit, canonical observation path for that owned setup
journal is implemented/qualified. Do not invent six binding fields, label zero
as fresh evidence, or claim that work-profile coverage also covers setup.

## Meaningful boundaries exercised

The 40 cases cover translation/replay and overlaps; checkpoint/lost-response
reservation; malformed scope/epoch/count/cursor/value atomic refusal; pending
gap/backlog; missing terminal or usage; counter regression; conflicting replay;
same-thread epoch handover; missing/changing/pre-campaign baseline; thresholds;
six shared reservations (including prearmed setups); cross-stream operation
collision; concurrent turns; prearm persistence/reconciliation and six-field
scope drift; early usage operation conflict; and late usage after settlement.
The final added case covers retired-stream admission after epoch handover.

Future integration should reuse these reducers and the separate response-loss
driver in a finite controller; it must also provide global pre-setup reservation,
actual baseline proof, durable CAS, timeout/interrupt/close ownership and continuing
replay. No claim that a complete M1 runner or real provider campaign is ready is
made by this preparation.
