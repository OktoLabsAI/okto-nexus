# Small F14/I06 follow-up after Root review

Same frozen R7 installed source `01b0de385398950ac4547aa8a5dcbc29473c12cb` and wheel `18c948b49844c7c551360732970fdc2ba91cba50075b73c1a7472571775d7681`. Two new own Temp fixtures/profiles, one run each; no F05 repetition, provider, personal state or product/test/original-helper edit. Actual RuntimeSession GET responses are captured before browser creation in `control/remaining-session-metadata.json`: identity is under **body.scope**, not top-level session_id. This preflight checks server/executor/binding/workspace/workspace-binding/session against the admitted owner. Previous events/target captures were not misrepresented as raw RuntimeSession responses.

## F14 — retained exact detail through reload and history

`cuts/r7-history-small/qualification.json`: **9 positive checks, zero failed assertions**. Only two sessions are seeded canonically: older A CLOSED and B READY. The test clicks A's actual delivery's View result button. Reload and native beforeunload acceptance use explicit CLI commands; product guards are not disabled. Reload and Forward preserve the complete target and every field of the RuntimeSession scope captured during preflight. Back returns to Home without a target/modal. A separate invalid reference gets403/404, performs no latest/sibling session read and no write.

The outer runner reports INCOMPLETE after the last successful script because it compared status strings PASS_SUBSET and PASS_BROWSER_SUBSET. This wrapper mismatch is preserved in `remaining-failure.json`; it is not a failed functional assertion. No repeat was used to hide it. Browser result files and the full canonical preflight scope are available in the base cut and `remaining-cuts/r7-history-small/`.

## I06 — fresh questions, real dirty guards and logout

`cuts/r7-dirty-small/qualification.json`: **8 positive checks and one failed observation oracle**. The fixture first creates only two terminal/retained baseline sessions in two canonical projects. It publishes distinct operator questions A/B only after the browser, scoped Home and capability-negotiated action are ready. Each request keeps its original120s TTL; both have more than60s left at the first interaction. No request is renamed, renewed or replaced.

Observed criteria:

- A's exact session is on the canonical form. Select synthetic option0, Escape, Keep editing: the same field node/value and occurrence remain.
- The actual UA `:modal`/effective inert state prevents operating the external Project selector while the form is open. No forced DOM change or selector bypass is used.
- The test refocuses the answer before the second Escape. Explicit Discard closes A; real Project selection moves to B. B is a distinct canonical request/session, with no copied A answer. This proves the actual modal-and-discard path; it does not claim a separate reachable Project-change-cancel prompt while the modal is open.
- B is edited, then the fixture canonically logs out its own operator session. The actual401 and protected-panel/answer removal pass without Apply or manual dismissal. Browser POST count is zero.

The last observer was attached after logout and missed the first UI401, so its denials[] assertion remains failed. `remaining-cuts/r7-dirty-small/offline-ui-denial.json` derives only what the complete already-finished ASGI capture proves: two actual401 GETs for B's native session/events, distinct from the auth script's APIRequest to Home. It does not invent a page event, rewrite the failed assertion or perform another interaction.

## Bounds and closure

Both browsers and owners exited normally0, with no signals, remaining sampled children, own process command lines or listener. The data, raw private wire and credentials remain in Temp. Unanswered-question runtime.close may hit its bounded unknown outcome; that is not relabelled as a confirmed per-session close. Normal canonical owner drain completed within the180s supervisor waiting bound, independent of native authority/TTL. Sampling every0.25s cannot inventory every short child.

CAS values and cookie/storage/wire contents are not published; public copies are sanitized and byte-pinned. Final installed payload comparison is **1,031 files, zero mismatches** (`remaining-payload-end.json`). These are functional observations with explicit harness-oracle limits; no performance, real-provider, reader/AT, human/default or whole-plan acceptance is inferred. Root owns scenario promotion and ledger decisions.
