# M06/M07 — Reconcile confirmed closed sessions and receipt history

This increment implements bounded reconciliation of durable receipt summaries and confirmed closed sessions after a Connector reconnect. It retains the scope and acceptance criteria of DELIVERY_PLAN.md. Active ownership adoption, nonzero event recovery, authority renewal and complete release acceptance remain open.

## Implementation

Connector publication storage advances additively to schema 3. Exact HTTP acknowledgments mark receipts as acknowledged instead of deleting their operation/hash associations. Pending publication capacity remains 4,096; acknowledged history is retained within the SQLite physical size limit. Metadata has a corruption checksum and includes the opening owner generation and stream epoch. New receipt revisions use the public Core reducer, and an old acknowledgment cannot erase a newer fact.

The reporter reads only public Core journal and ownership APIs. It compares stored R4/Core associations, projects current receipts, scans claims in pages of 128 and answers Server operation pages of 256. It never executes a native action during recovery. Missing receipts, absent claims, occupied resource slots and unknown ownership keep recovery unresolved. If a Core fact advanced after acknowledgment, it becomes a pending HTTP publication before control readiness can be granted.

A released claim requires the persisted opening identity/generation/stream epoch and a Core SUCCEEDED close associated with that generation. A new Core host can establish this from durable data without retaining a native process handle. Nonzero stream watermarks keep recovery blocked until event ingress/replay is implemented.

The Server correlates every page to its current owner, connection generation and reconciliation cursor. It checks summaries against checksum-verified canonical receipts, requires a durable matching SUCCEEDED close, and closes the session only on that evidence. Final readiness additionally requires no active sessions, no unscanned operations, no receipt insertions since the scan snapshot and no incomplete evidence. Readiness changes through the current owner's compare-and-set.

WSS frames use the existing Core limit of 1 MiB, so a legal 256-receipt report can exceed 64 KiB. Individual operation payload limits are unchanged. Reconciliation has separate bounds for recovery cycles and continuation pages.

## Verification

The HTTP/WSS integration now has eight scenarios, including ordinary publication, lost delivery, lost acknowledgment, a Core commit before failed projection persistence, confirmed close reconciliation and a history larger than one page. The paged case reconciles 264 nonterminal receipt summaries in two pages. Its first report exceeds 64 KiB. It uses 260 seeded durable historical facts, not 260 provider turns. The original five canonical native actions are executed once.

Twenty-seven focused Server tests cover successful readiness, changed hash/revision/stage, missing or corrupt receipts, unknown claims/processes, stale owner generation, absent close/proof/watermark, nonzero watermarks, a receipt inserted after the snapshot, stale connection/cursor/scope, duplicate facts and changed Server ownership. These tests seed durable preconditions; authenticated real ingress is covered separately in the WSS integration.

Connector tests cover retained acknowledged history, monotonic receipt advancement, stale acknowledgments, corrupted metadata and 257 Core claims over three pages. Unknown claims remain UNKNOWN, and a stale continuation cursor is rejected. Existing publication, authorization, startup and cancellation regressions remain part of the installed campaign.

The first focused Server fixture incorrectly attempted authenticated ingress without a dispatched lease and was correctly rejected. It was changed to explicitly seed the durable precondition; production ingress was not weakened. Earlier integration fixture corrections joined the old execution owner before closing its socket and marked possible effects before recording synthetic SUBMITTED history.

## Compatibility and limits

- Schema 1/2 rows are preserved, but associations previously deleted by old versions cannot be reconstructed. Older opening rows without persisted generation/epoch do not become release proofs.
- Active session adoption, renewals/rotation, nonzero event ingress/replay, embedded recovery, crash/pressure qualification and migration rollback remain pending.
- History pruning is not qualified. Per-session open/close lookup is bounded at 256 records and refuses overflow. Claim and control scans have explicit page budgets.
- The shared Core remains 0.2.35.dev0 with SHA-256 20013ae173652ea3726f5b7ae5d7c37e66eac8f9bc319ae3c36f84e70247e760.
- This campaign uses technical native peers and fixture readiness. It adds no Pi/Codex/Claude provider qualification or independent-host acceptance.
- Existing user UI assets are included in the Nexus wheel without new UI acceptance. Full M00–M13 and G0–G3 requirements remain unchanged.

## Evidence

[Installed campaign](test_runs_20260930_reconciliation.json), [wheel hashes](evidence/reconciliation-artifacts.json), and [installed runner](run_reconciliation_installed.py). The runner verifies wheel, installed package and current source bytes for all three packages before invoking pytest from an external working directory with Python isolated mode.
