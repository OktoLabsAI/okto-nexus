# Board panel review

Read-only source review of product commit `23953579`. No new browser execution, global test, build, provider call, or product mutation was performed for this review. The frontend implementation and focal qualification remain recorded in [pr20-home-board-frontend.json](pr20-home-board-frontend.json) and [pr20-home-board-frontend.md](pr20-home-board-frontend.md). Root reported the final 328/328 Node tests and TSC/Vite passing; those are antecedent execution results, not a new result from this review.

## Exact targets and controls

- `homeEntryInspection.ts` preserves the explicit Server/executor/project/session tuple from session, execution, or result targets. An implicit selection requires exactly one proven session relation; list ordering does not select a recent session. Multiple relations require explicit selection.
- `HomeEntryInspection.tsx` forwards each selected result target unchanged to `HomeInspection`. Session choices use the full tuple as their key. `ExactEntrySession` resolves the exact canonical target before exposing output; `homeSessionInspection.ts` additionally compares all seven admission identity fields, including binding and workspace binding. Failed lookups select no replacement.
- `HomeInspection.tsx` resolves the target canonically and checks availability before rendering the original inspector. `homeNavigation.ts` validates the scope and exact returned target, including execution/result operation ID and external generation. Session/connection contexts receive additional tuple checks.
- Continuation requires an explicit action. `continuation.ts` rereads the exact session and binding, checks the complete admission scope and continuation availability, and rejects closing/released/unavailable contexts. The continuation component receives `canStart=false` and the exact continuation scope. Opening a result does not submit a continuation.
- Related pagination retains the selection's `entry_revision`, group ID, entry ID, Server and normalized filters. `assertEntryInspectionPage` rejects a changed relation revision or foreign context. Its revision is deliberately distinct from the global Board revision. Authorization failures clear the panel's protected related state; other paging failures close its cursors.

## Viewing preferences: two distinct freshness contracts

The overview callback in `OperationalHome.tsx` reads `current.current.board` and uses the Board-aware `freshHomeEntryOccurrence` helper. It refuses paused, pending, loading, unavailable or stale-section contexts, requires matching occurrence and preference revisions, and locks the occurrence while its single request is pending. Failure triggers refresh without replay.

The detail callback in `HomeEntryInspection.tsx` uses its captured occurrence snapshot. **It does not perform a fresh Board lookup before Seen/Snooze.** Both requests include the captured `source_revision` and `preference_revision`; `AttentionService._preference` authenticates the principal, reprojects the exact occurrence through its authorized query, compares both revisions inside its UoW, and returns conflict when either changed. The persistence call also receives the expected preference revision. A changed global Board revision alone is not this endpoint's CAS token and can concern another card.

The detail locks concurrent requests per occurrence, invalidates further local preference actions after a success or an unconfirmed failure, asks the user to reopen, and does not replay. HTTP 401/403 clears protected state. These preferences do not acknowledge a receipt, answer a question, impersonate another agent, or authorize execution. Parent reviewed this distinction and retained the endpoint CAS as the authority; no additional dependency on paused presentation was introduced.

## Conclusion and limits

No missing CAS or cross-scope target substitution was found in the inspected paths. The captured detail snapshot is an explicit freshness limitation, not proof that a stale detail preference always succeeds or that it was freshly looked up in Board. Questions, approvals and execution controls retain their own canonical inspectors and revalidation.

This is a source review. It does not add browser proof for concurrent detail preferences, native application of a decision, provider activity, human understanding, or a complete lifecycle. No human failure or unexecuted scenario is promoted to PASS.
