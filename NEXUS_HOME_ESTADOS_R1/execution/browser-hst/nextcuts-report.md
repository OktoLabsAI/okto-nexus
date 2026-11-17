# R7 decision and contextual browser cuts

Installed R7 source `01b0de385398950ac4547aa8a5dcbc29473c12cb`, wheel `18c948b49844c7c551360732970fdc2ba91cba50075b73c1a7472571775d7681`. Only new execution files and private derivative fixtures were written. Product, canonical tests, original helpers, old cuts and prefix remain unchanged. All peers are synthetic protocol fixtures, with canonical Identity/Setup/TestFake/Finish/admission/decision owners; no real provider or personal account. Functional runs may share CPU with other validation; no performance claim.

## Decision cut: D11/D12/H05, by criterion

The first attempt is preserved in `cuts/r7-decision-bell-wait-antecedent`: an immediate assertion preceded bell item loading; one positive/one failed precondition, zero decision POST, zero durable decision/write. Normal exit0 and physical absence.

The fresh derivative is in `cuts/r7-decision-race-recovery`, with additional canonical snapshots under `nextcuts/r7-decision-race-recovery`. It records ten positive assertions and one failed **test oracle**, not a product failure. The oracle inspected Home sessionStorage while either context could win the race. That failing result is unchanged.

| Criterion actually captured | Result / boundary |
|---|---|
|Two separate browser contexts, exact question/session through Home and global bell|Both forms review the same canonical request and session. Bell has one matching occurrence. No recipient reassignment.|
|Two explicit stale-screen submissions|Exactly two browser POSTs, canonical202 and409. Transport obtains the first real accepted response then drops it; the second request is held until first acceptance. Browser submissions overlap, but simultaneous database transactions are **not** claimed.|
|Lost response recovery|The completed ASGI capture contains five200 GETs for the same decision ID and no third POST. The script executed Check native decision in both contexts; GET capture does not distinguish button-triggered from automatic recovery or attribute each GET to its context.|
|Same accepted intent and one durable effect|Read-only before/after snapshots prove one decision, its original accepted client-intent ID, one native write operation and one canonical receipt revision1/stage SUBMITTED. Full server/executor/binding/subject/workspace/session/owner-generation and operator actor are preserved. Productive open/turn operations are unchanged.|
|Winner storage|**Not captured.** Storage from the other tab is not substituted for it.|
|Honest application text|The dedicated final assertion was not reached after the oracle failure: **NOT_RUN in this cut**. SUBMITTED is not native application/resumption proof. No D08 claim.|

`nextcuts/r7-decision-offline-derivative/qualification.json` adds only assertions against these already completed captures. It does not rerun the race or rewrite the original failed browser result. It proves total POST count, repeated same-receipt GETs, accepted host intent, one decision/write/receipt and no new productive operation. Scenario-level promotion belongs to Root; this report does not relabel the three entire scenarios PASS.

## Context cut: F05 observed; F14/I06 remain incomplete

Three finite attempts are preserved, all with zero browser POST:

| Attempt | Observed result | Cleanup |
|---|---|---|
|`r7-context-beforeunload-antecedent`|Two setup checks. CLI yielded at the native beforeunload dialog and did not return the function's later JSON. Do not infer F05 PASS merely from execution reaching a later line.|Own group CTRL_BREAK after the external100s drain bound; exit3221225786. Data preserved and physical absence independently confirmed. **Not normal0 or timeout-free.**|
|`r7-context-offpage-known-session-antecedent`|Known session happened to lie outside page1; the test's first-page assumption failed before additional effect. No substitution by newest/first session.|Normal0; no signals; physical absence.|
|`r7-context-paging-history-partial`|Two explicit setup checks and three F05 checks passed. Bounded canonical paging finds the original known session, explicit Refresh sessions restores a genuine cursor, a new session is admitted canonically, then real409→current200 occurs in the same DOM panel with the same selected tuple and no mixed/duplicate option IDs. Reload keeps the exact full target. The next oracle wrongly checked top-level session_id instead of RuntimeSession.scope.session_id.|Normal0; no signals; physical absence.|

F05 has direct network/DOM assertions in `context-finish-result.json`; it need not be repeated. F14 has only the positive reload/full-target subset. Back/Forward and invalid-reference phases were not reached. I06 was not started before the original native question expired; it was not renewed or replaced to salvage the case. A smaller follow-up for F14/I06 is being prepared separately and requires its own post-DOM window and Root review.

All five attempts have closed browser/fixture processes and no remaining own listeners. The bounded canonical runtime.close helper can report unknown for an unanswered native request; no confirmed per-session close is invented from an outer process exit. The last normal drain allows180s for the finite active-session cohort; this changes supervisor waiting only, not grant/lease/question authority or TTL.

All native request TTLs remain their original120s. No blind reply, task retry, grant renewal, SQL frame/identity/authority mutation, fake API success or personal browser/profile was used. Cookie storage, raw wire and unredacted CAS stay private in Temp; public copies are sanitized and pinned. The runner verifies the frozen installed payload before allocation; a new final payload scan is deferred during the exclusive large-DOM window rather than introducing measurement load. Earlier package guards remain separately documented.
