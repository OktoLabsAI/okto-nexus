# Navigation browser follow-up — conservative scenario coverage

The real browser served `index-BGONNtiX.js`, SHA256
`dfef7675dea3918117e0df676e3e6d1ef72dd03dec61086e0d24a1b91f6430c9`,
with the actual checkout HTTP routes and SQLite fixture. No GET response was
mocked, no provider/native executable ran, and neither browser issued a POST.

## T-NAV-08: PASS within canonical inert-fixture boundaries

The first browser was already in Graph (`ae9311`) before its own trigger.
The canonical event ingestion service received a new sequenced native input
request for the admitted operation/channel/session. It generated a new approval
(count 1→2, `arrival-Graph.json`). Publication was acknowledged before the bell
click. The browser still reported Graph before opening the bell (`46b1b9`),
then opened global Needs attention. The exact new native_question_pending item
appeared as a real DOM row (`67d8f6`). graph-new-question.png retains the queue
viewport; the exact row may be below that viewport. Global requests
contain no workspace filter; no Advanced or Home hop was used.

The first Artifacts attempt proved the new row but did not fence its publication
acknowledgment before the bell click, so its temporal given is retained only as
a subset. A second own fixture removes that ambiguity. The browser reached
Artifacts first (`2b3dad`); triggers then committed two new native requests
(the first preserves the event sequence), and arrival-Artifacts.json was read
before continuing (`c68c4c`). `5e78b7` asserts the browser remains in Artifacts
and the exact new question already exists, then clicks the bell and waits for
that exact global row in real DOM. artifacts-only/new-question.png retains the
queue viewport and count; the exact row assertion is the DOM locator rather
than a claim that the row is inside the captured viewport.

This qualifies arrival/opening the global queue, not native application, speech,
an automatically incremented bell count, or delivery through an actual provider.
Question ingestion uses the same canonical commit_execution_events API as the
existing native fixture; it does not fabricate HTTP DTOs or insert approvals.
The heartbeat uses canonical WSS and lease renew/applied; authority, recipient,
nonce and TTL were not overwritten. The first fixture later refuses a renew
because its inventory is no longer fresh and records peer_failed; this occurs
after both arrival publications and is retained in liveness.json. No long-lived
lease/readiness claim is made. The second fixture has no peer error.

## T-NAV-05: visibility PASS; full direct-link given unavailable

`a210c3` reads actual Server feature_memory=false, verifies Shared memory is
absent from Advanced, and demonstrates that the unknown `?view=Memory` query
opens Home. The actual scoped Memory endpoint returns 200, preserving the
existing API contract. There is no generic view URL parser in App: only the
allowlisted home_target has a product link contract. Therefore this unknown
query is not promoted as a supported direct Memory link or a backend refusal.
Full scenario remains NOT_RUN for that missing given. Navigation never toggled
the Server feature.

## T-NAV-04: full given NOT_RUN

The application starts view at Home and has no saved-view preference or generic
view bookmark input. It persists project and other independent preferences.
resolveNavigationId maps legacy Meta-harness to the Conversations-labeled
logical ID and Policies to itself for callbacks, but is not an implemented
saved-selection entry point. No artificial storage key or React state was
injected to claim the missing given. An extra callback-only browser probe was
interrupted while awaiting an exact Policies accessible-name locator
(`bea31f`); it is not a passing alias/saved-selection test. This gap requires a
product decision and cannot be closed by inventing a URL/storage contract in
the fixture. No product change was made.

## Cleanup and limits

Both browsers were isolated in ui-r1-nav-arrival and closed. Both fixtures,
canonical peer threads, WSS and SQLite factories exited 0 (`863ed5`, `f4baad`).
The wrapper only permits native decision POSTs, but the recorded HTTP journals
contain zero POSTs. Four exact own Temp allocations, including an unused
preparation copy, were physically removed (`278270`, cleanup.json). Only code,
public IDs, sanitized diagnostics and screenshots are retained; raw homes,
SQLite stores and fixture keys were deleted. No paid campaign, personal login,
proposal, package, ledger, Git or product was touched.
