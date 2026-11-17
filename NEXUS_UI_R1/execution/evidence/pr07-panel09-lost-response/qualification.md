# T-PANEL-09 — lost native decision response

PASS for the declared browser/HTTP/SQLite scope. The BXP compiled client was
served by an own loopback Server with the intact human-origin canonical fixture.
Native peer/version/lifecycle remain synthetic; no provider was executed.

The browser answered the actual human question once. Playwright `route.fetch`
sent the unchanged request to the actual handler and received 202; only then
`route.abort` interrupted the response to the application. No POST response DTO
was fabricated. `Check native decision` recovered the same decision through
canonical reads. UI displayed CONFIRMED / DISPATCH_PENDING and explicitly said
that a recorded decision does not prove application by the provider (tool
`1c5fd0`). Reload then read the exact approval and matched its decision ID.

The same approval was reopened using its canonical `home_target` link. This
inspection renders Executed result rather than the actionable component's
`canonical-native-status` node. An additional assertion incorrectly waited for
that node and timed out (`6297ec`); the subsequent snapshot (`8171f3`) and DOM
read (`c6ed5d`) retain the same decision ID, DISPATCH_PENDING and inspection-only
message. This is a retained selector-oracle limitation, not a second decision
or evidence of native application. The current helper's reload UI assertion
must use the inspection's result presentation if reused.

Final read-only SQLite evidence: one execution_decisions row; one exact
input.provide operation by operator for subject/session; one matching row in
execution_dispatch_outbox. `final-db.json` initially counts delivery_outbox=0,
which is the unrelated legacy delivery table. `exact-outbox.json` separately
queries both tables and proves execution_dispatch_outbox=1 without rewriting
that antecedent. The Server journal contains exactly one POST, to the native
approval-decisions endpoint. Recovery/reopen caused no second productive POST.

The copied fixture changes only repository-path resolution, additional read-only
summary queries and logging of the optional renew return field. The prior
logging KeyError is avoided with `.get`; canonical renew/applied is unchanged.
The peer sent 47 canonical WSS heartbeats and completed three renew/applied
cycles; all 14 captured authority checks were current, no peer error occurred,
and the thread joined. The existing controlled clock and proposal/nonce/lease
authority were preserved; no TTL, recipient, permission or DB freshness edits.
This does not claim a 180-second wall-clock lease test or native response
delivery/application.

Browser session ui-r1-panel09-lost closed (`c570c6`). The finite fixture exited
0 (`581ddd`); its two open SSE readers were cancelled during bounded HTTP
shutdown. The screenshot was captured after stop and shows the retained
inspection DOM; resulting network-disconnect console entries are not a claim
of a clean live console. Both exact own Temp allocations were removed
physically (`a2cdb2`, cleanup.json). No raw DB, keys, cookies or provider data was
copied into evidence. No product, proposal, package, ledger or Git was changed.
