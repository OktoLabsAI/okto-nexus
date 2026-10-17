# M4d3: terminal sessions without a native stream

Status: installed qualification passed; global rollout pending. This checkpoint addresses the no-stream
retirement gap in M4d; initial directory audit, scan caps and stream scheduling
remain separate acceptance items.

Build and test directories use the working label `m4d2`; the canonical ledger
already assigns M4d2 to independent historical maintenance. This extension is
M4d3. Existing reports retain their original paths for traceability.

No stream is not evidence of no execution. Two positive paths can retire a
terminal session without inventing a native stream or EXITED proof:

1. An authenticated initial lease denial, persisted as the exact Core refusal,
   whose capacity and tool cleanup have completed.
2. A terminal dispatch/preparation refusal before the local publication/Core
   boundary, with fenced producers and empty exact session resources. A pending
   opening that has not been dispatched remains eligible for its first execution
   and must not receive this checkpoint.

Both use the canonical session retirement field with a distinct release kind;
the checkpoint records the original opening/generation and the evidence source.
The SQL commit rechecks terminal/no-lease state, absent streams/events, exact
proof and a revision captured before validation. Mutating or removing the
supporting dispatch/denial evidence invalidates the checkpoint transactionally.

Historical maintenance discovers no-stream sessions by their opening operation,
without weakening the existing streamed release path. Cleanup or commit failure
leaves the obligation pending. Occupied physical slots still override retirement
at startup. Restart may skip only an already committed exact checkpoint.

Qualification: reproduce the existing repeated-history behavior, check both
proof paths, cleanup/commit cuts and stale evidence, absence of manufactured
streams/results, pending opening retention, occupied slots and repeat restart.
Use deterministic native peers and installed wheels; real UI gates stay at the
major milestones defined by the parent plan.
