# M05 — Readiness after retained-resource reconciliation

Status: released-resource recovery integrated; complete M05/G1 acceptance remains open.

After receipt and event recovery, serve validates retained session journals against canonical local opening records and the shared slot ledger. Missing stores and untracked files are refused. Both Core ledgers must report no occupied reservation. Each journal must expose exactly the expected claim, opening operation and released shared-slot state. Core's public release projection correlates the claim and durable opening receipt with the original owner generation. Provider binaries and credentials are not loaded for this scan.

Event recovery precedes resource reconciliation. Every retained session must have a matching contiguous Core/Server watermark and no pending Server gap, including already-closed sessions. The existing canonical reconciliation reducer consumes the historical receipt summaries, release proofs and stream watermarks. Its readiness transaction also verifies the live embedded store owner/epoch. A release closes the historical session without inventing a runtime.close operation. Only a complete accepted reconciliation enables the serve-owned dispatch pump.

The scan is bounded to 32,768 session records, 256 ownership pages of 128 rows per store and 128 canonical reconciliation pages. Exceeding these budgets leaves recovery incomplete. Unknown or occupied resources are not released by assumption; process adoption/containment under crash uncertainty remains separate required work.

## Verification

The directed source campaign passed five cases. Real serve shutdown persists native stop/release, then the successor boot returns CONTROL_READY and admits/executes a new session through the public API using the approved binding. Negative cases retain RECOVERING for an occupied global ledger, missing ledger, untracked journal and event gap. Existing receipt/event restart tests now require readiness after proven release. Native execution and contract qualification remain technical fixtures.

Installed regression results and wheel hashes are recorded in test_runs_20260930_embedded_resources.json. Tests run with isolated imports outside the checkout and compare installed package bytes against source and wheels. The no-Connector environment is a real environment without that application; its tests overlap the normal suite.

Final installed results: 113 passed in the normal environment and 58 overlapping cases passed in the actual no-Connector environment, with pip check.

## Remaining fixed-plan work

Recovery/adoption or containment of genuinely uncertain native processes, definitive pre-effect failure handling, complete event consumption, vault/tools, approval/input and real Pi/Codex/Claude public journeys remain required. Pressure, platform and final release qualification remain open. No milestone or gate closes in this increment.

Core and Connector artifacts are unchanged. The Nexus wheel includes preexisting user UI edits excluded from this commit and UI acceptance. The existing Starlette/httpx deprecation warning remains.
