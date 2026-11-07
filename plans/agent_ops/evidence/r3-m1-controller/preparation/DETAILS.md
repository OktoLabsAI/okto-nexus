# Finite M1 accounting/control composition

Preparation only. No product files are modified. The only executable entry
point is `run_synthetic.py` with the pinned installed Q environment; it accepts
no provider, service or productive campaign arguments.

## Components and scope

`controller.py` composes the frozen token collector and response-loss driver
through their existing interfaces. One controller holds an exclusive Windows
file lock for its lifetime; a second instance is refused. Call `close()` before
restoring a controller. Checkpoints are flushed before dispatch. Scope is two
lane labels and at most six total reservations, including setup, useful work
and continuation. The counter never resets on response loss or observer reload.

The current local standalone setup source is Nexus
`<owned home>/connection-tests/<UUID>/journal.db`. The installed
`application/connection_test.py:143-238` creates this private Core journal under
the namespace `connection-test/local/session/epoch`; it does not publish setup
usage through canonical Server session replay. The monitor does not fabricate
binding/workspace revisions or a test_id relationship that this source lacks.

Setup attribution is one pre-effect serial reservation, an owned campaign home,
an initially empty setup root (or only earlier attributed and closed journals),
and exactly one new UUID journal. Additional ambiguous journals, path links,
replacement, counter regression, malformed counters and missing/gapped events
stop admission. Old journals remain retained and monitored for late usage.
Only read-only SQLite projections of sequence/correlation/usage/receipt metadata
are read; prompts, tool bodies, output text and authentication data are not read
or copied by the monitor. JSON booleans cannot masquerade as integer token counts.

Setup settlement requires the exact standalone namespace, correlated started
and terminal turn, at least one usage observation, caught-up replay, terminal
turn receipt, a close receipt and release of the corresponding owned open slot.
For this non-R4 context, installed Core `close_runtime.py:78-88` waits for
physical shutdown and records close as `SUBMITTED`; it uses `SUCCEEDED` only
with R4 authority. Therefore the monitor accepts either close stage only together
with `owned_slot_reservations(open).released=1`. A negative test removes that
release bit in its own synthetic journal and proves close SUBMITTED alone is
insufficient, then restores its fault in `finally`.

No separate Connector setup journal is assumed. The inspected Connector
connection-config command calls the Server setup endpoint; that endpoint selects
the embedded owner. The remote M1 lane performs a setup test only if its actual
canonical path does so. Normal Connector work must use the same canonical event
replay source as other runtime work. No unobserved consumption source is admitted.

## Operational interface

The caller supplies the existing TerminalWork objects, bounded operator HTTP
transports and exact already-reviewed service stop callbacks. The module never
constructs provider/OS commands, reads a vault or approves a native request.

1. Construct or restore `Controller(state_path, campaign_root, create=...)`.
2. `attach(lane, flow)` and `attach_owner(lane, exact_home, stop_callback)`.
   After a restart during setup, `attach_setup_stop(request_id, exact_home,
   stop_callback)` verifies the retained owner. No new dispatch is permitted
   while a required stop capability is missing.
3. `setup(id, lane, home, dispatch, stop_callback)` reserves durably before the
   existing setup HTTP call. `work(id, lane, text, stage=...)` reserves globally
   and in the collector before TerminalWork submits. Initial work uses explicit
   new-session intent; later work retains its known session.
4. Poll at least once per second while effects can be active, with bounded HTTP
   calls. Poll canonical pages for all retained work streams and metadata from
   all owned setup journals. Response-loss recovery reads the same canonical
   intent with GET; it does not call an admission-capable resume method.
5. At 100k observed tokens, a gap/malformed/unknown observation, missing turn
   usage, or an unsettled request age of 120 seconds, select only the owned
   canonical interrupt/close. If the work session cannot be resolved, or the
   operation is standalone setup, invoke the exact owned service stop callback.
   The selection is saved before dispatch and is never blindly repeated.

This is a polling controller, not a service supervisor. Its deadline is checked
when polled; it does not guarantee instantaneous cancellation while a transport
is blocked. The final campaign caller must keep polling during active work and
retain canonical stop receipts/status. `stop_selected` means an attempted
canonical stop, not proof of OS exit. Callback failure leaves uncertainty and
blocks further productive work; no process kill, authentication workaround or
new productive attempt is substituted.

Known totals sum setup and canonical-work high-water observations, without
double-counting replay. The preventive threshold remains 100k; the proposal's
operational tolerance is 700k. A terminal plus caught-up usage observation can
settle the serial admission operationally; it is never called final, billed or
an atomic hard cap. Late usage on old sources remains monitored.

## Synthetic validation and boundaries

Tests use installed Nexus/Connector/Core imports from Q, real ASGI/SQLite/Core
contracts, a synthetic native factory, and real installed ConnectionTests.run.
They deny Popen and Windows credential functions. The setup abort callback uses
the installed service-lifecycle shutdown hook and checks its task/native peer
finish; this is not OS task/service qualification. Connector network execution,
provider login, inference and M1 acceptance remain unqualified here.

The combined test runs two standalone setups in the same owned home, preserves
both journals, then work and continuations. Six reservations include both
setups; the seventh is refused. It verifies persisted pre-effect reservations,
same-ID recovery after discarded admission response, actual canonical event
pages, combined usage, no duplicate work POST and no duplicate synthetic turn.
Other cases cover threshold, 120-second age, missing usage, gap, malformed bool
usage, reload stop capability, two-controller exclusion, uncertain unresolved
work and multiple new setup journals.

The first run `synthetic-run-00z4nw2h` is diagnostic and **not accepted in full**:
one monitor assertion required the wrong close stage, and an artificial pending
gap held fixture teardown. With explicit root instruction, only that exact
owned gap was restored after comparing its expected record; the intervention
and final XML are retained. Its 12 passing cases are not promoted separately.
The monitor now matches the standalone close contract; the gap test registers
a finalizer that removes only its own injected gap on every exit.

The next run `synthetic-run-ekodn597` passed all 13 cases without intervention.
The final run `synthetic-run-gtxuhy58` passed all 14 cases in 99.763 seconds,
including the explicit unreleased-slot negative. This is 14 distinct final cases,
not the sum of passing executions across runs. Input hashes before/after and loaded
product-module path checks accompany each run. Private test homes/databases and
controller/checkpoint contents are excluded from the public artifact set.
