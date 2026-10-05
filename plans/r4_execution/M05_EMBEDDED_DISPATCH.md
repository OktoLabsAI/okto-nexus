# M05 — Serve-owned embedded outbox dispatch

Status: partial M05 integration. Production qualification and G1 remain open.

## Implemented path

The serve lifespan composes an embedded dispatch owner after inventory and approved-launch composition. It starts only when the existing R4 qualification gate is enabled. A fresh local executor becomes CONTROL_READY under the current store epoch and exact embedded generation after checking for unresolved sessions/operations and retained Core stores. Retained stores or unresolved work remain RECOVERING pending explicit cold recovery.

The owner uses the canonical outbox reservation/send pump. HTTP admission no longer needs a caller to reserve or send the local operation. Productive operations share a per-session gate; controls can proceed while a turn waits. The database reservation retains its existing regular/control item and byte limits. Execution producers remain owned through shutdown and canceled cleanup observers.

Initial execution loads the approved local mapping, requests the canonical lease, installs it in Core and acknowledges it to the Server. The owner uses Core's public operation context and typed open/turn/steer/interrupt/close operations. Leases renew at half the remaining Core deadline under each session's productive gate, through independently retained renewal tasks. One blocked gate does not stall other sessions' renewal or publication. Close removes the active session only after a successful Core receipt. Approvals/input and session tools are not integrated by this increment.

Migration 084 persists Core's non-secret receipt binding before native effect. A bounded, paginated publisher reads host-owned journal facts and uses Core's verified projection. Receipt persistence reuses the canonical reducer and state projection, authenticated by the current embedded store owner without a fabricated remote ticket. Repeated facts do not allocate a new revision. Terminal publication obligations are marked complete after durable receipt acceptance.

The crash window between terminal receipt acceptance and publication completion is recoverable: observing the same terminal fact completes the pending obligation without creating another receipt revision. Even receipt replay requires the current embedded owner.

Dispatch/publication failure stops further dispatch, moves the current embedded owner back to RECOVERING and retains the uncertain outbox state. The host starts owned Core shutdown for containment; it does not manufacture a successful receipt or repeat the native operation. Cleanup drains the pump, publication task, execution producers and failure-containment task before the normal application teardown continues. A pump cleanup error still initiates Core shutdown and joins producers before propagating the error.

## Verification

The new tests use real serve startup, public local preparation/binding/grant/admission/history routes, canonical lease service and Core journals. They do not set CONTROL_READY or manually call reserve/begin. The native factory and contract qualification are technical fixtures; production readiness remains false.

Cases cover automatic open, turn, steer, interrupt and terminal close; stable HTTP retry IDs and one native open; zero WSS tickets; independent automatic renewal; controls while a turn send is held; stale owner refusal; receipt persistence failure without native replay and subsequent admission refusal; canceled shutdown observer retaining the producer; cleanup failure still draining Core; historical receipt access after removing the synthetic executable; and refusal to treat retained session journals or slot ledgers as fresh startup.

During source development, tests were corrected to use the public request shape and explicit interrupt target, the actual native verb, both legitimate owner-failure reporting paths, and the correct placement of a replay assertion. These initial failures do not represent a completed campaign. The installed campaign records the final result separately.

The first expanded installed campaign recorded 131 passes and one failure in the existing remote reconciliation test. JOURNAL_UNAVAILABLE cleared the transport's pending request but retained the reconciliation object's cached page/ID. The error path now verifies the link and current recovery owner, then resets that snapshot before requesting a new page. The original failed campaign and artifact hashes are retained with the `-initial` suffix. The directed corrected source run passed 11 cases before the final rebuild.

The final installed Nexus campaign passed 135 tests in 437.66 seconds. The actual no-Connector environment passed 47 overlapping tests and pip check. Both environments verified installed package bytes against the wheel and source before execution. The intermediate corrected campaign (134 and 46 overlapping passes) is preserved with the -pre-quiesce suffix; it precedes the final readiness/cleanup refinements. Counts across campaigns are not additive.

## Remaining fixed-plan work

Cold journal/slot recovery, historical-owner publication, event ingress/replay, session tools and vault, approval/input, platform/failure pressure qualification, and complete real Pi/Codex/Claude journeys remain required. Definitive pre-effect failures also need finer public outcome handling; this owner currently fences failures conservatively for reconciliation. Neither M05 nor G1 is closed.

The Core and Connector artifacts are unchanged. The Nexus wheel includes preexisting user UI edits, which are excluded from the commit and UI acceptance. The existing dependency deprecation warning remains.

See [results](test_runs_20260930_embedded_dispatch.json), [artifacts](evidence/embedded-dispatch-artifacts.json) and [installed runner](run_embedded_dispatch_installed.py).
