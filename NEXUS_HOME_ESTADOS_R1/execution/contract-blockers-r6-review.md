# Focused contract blockers before R6

Read-only review of four literal scenarios. No ledger/status mutation and no new runtime/test execution. Sources and exact line ranges/hashes are in the adjacent JSON.

| Scenario | Current contract | Safe reader behavior |
|---|---|---|
| HST-T-C07 | NO_QUALIFIED_CURRENT_INDEPENDENT_QUEUE_PRODUCER | Do not count a queued sibling as Working or use it to prove full pause is impossible. Preserve exact pending action and show unknown aggregate when independence is absent. A genuinely started productive sibling is covered by C03, not a substitute for C07. |
| HST-T-C08 | SAME_NATIVE_REQUEST_CONTENT_CURRENTLY_IMMUTABLE_END_TO_END | Retain the exact occurrence/action and known blocking fact; do not flip isBlocking from receipt arrival/time/UI status. A new native ID is a new occurrence and does not satisfy the same-ID Then. |
| HST-T-D02 | PERMISSION_ACTION_SUPPORTED_BUT_CURRENT_FULL_BLOCKING_PROOF_NOT_GENERALIZED | Show canonical Approval pending and its exact allowed action. Without proven suspension, keep blocking unknown/independent request rather than moving a harness merely because the kind is approval. No auto-approval/reply or native capability is added. |
| HST-T-D08 | NATIVE_CAUSAL_APPLICATION_RESUMPTION_ACKNOWLEDGEMENT_ABSENT | Awaiting confirmation with exact refs, zero new human response where already decided, and no replay. Current independent progress or terminal result may establish Working/Idle on its own merits, never claim that the answer was applied. This permits D09/B02 without fabricating D08. |

C07 is not closed by the now-proven C03 productive sibling: capacity WAITING/RUNNING is flow control, not independent queue admissibility. C08 is constrained by actual producer immutability, even though the Core reducer can model higher revisions. A new native request ID cannot satisfy the literal same-occurrence transition.

D02 supports the permission action and pending badge, but its full blocking Given is not currently demonstrated outside the exact Codex requestUserInput proof. Do not apply that boolean contract to tool approvals, Pi or Claude merely because a request is pending.

D08 remains blocked by absent native causal acknowledgement. The decision bridge verifies the exact typed write operation, not native response consumption/resumption. R5 terminal Idle and independent Working can be shown without asserting application of the answer.

Evidence boundary: R5 installed251 PASS (scoped suite) and browser main28 checks are referenced as actual positive/control proofs. No R6 browser, real provider, AT, human or physical multi-host acceptance is inferred. No general reclassification of the other partial scenarios is proposed.
