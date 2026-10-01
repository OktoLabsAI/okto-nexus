# NS15.03 canonical domain recovery — October 1, 2026

The legacy outbox maintenance caller now accounts for its canonical execution
mapping. It previously consulted only the legacy dispatch owner and harness
session rows, which cannot prove that an R4 effect is absent or stopped.

Pending cancellation checks every associated canonical dispatch state in the
same writer transaction as its reconciliation marker. Only PENDING/RESERVED
operations qualify; canonical begin-send revalidates that marker. A pending
domain projection cannot conceal an already crossed canonical send fence.
Other claim recovery requires associated canonical sessions to be CLOSED with
CLOSED leases, in addition to existing exact-snapshot, operator, audit and
explicit duplicate-risk requirements. Canonical terminal results receive the
same protection as legacy terminal results. Pre-send refusal projection does
not overwrite an operator's reconciled cancellation.

Operator detail inspection includes bounded canonical operation/session scope
and state, so the operator can identify the session requiring closure. It does
not expose prompts or credentials. Existing legacy recovery remains supported.

Public tests hold a native send after its effect but before receipt publication:
domain state is still PENDING, cancellation returns conflict, and MCP pull stays
excluded. Separate tests cancel before any native open and recover an accepted
claim only after confirmed canonical close. Existing MCP consumption and legacy
recovery/backpressure tests run against the installed final wheel.

Legacy fixture corrections replace retired stdio recovery with refusal plus HTTP
recovery, derive the migration tail from published SQL, and exhaust the outbox
byte budget through bounded HTTP requests. They preserve the original recovery,
migration and quota assertions without reopening removed product surfaces.

Evidence: `run_ns15_03_recovery.py` and
`test_runs_20261001_ns15_03_recovery.json`. Native peers and readiness remain
fixture-qualified. Capture retention, subscriber parity audit, cross-protocol
fallback, native loader removal and final restore/release remain pending.
