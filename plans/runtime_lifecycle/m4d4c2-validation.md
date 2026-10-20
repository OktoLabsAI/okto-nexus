# M4d4c2 — Nexus physical ledger binding

Status: selected source and installed-wheel validation passed. This
is a technical checkpoint, not the completed audit frontier or a global rollout.

Core 0.0.12 M4d4c1 persists a random identity inside the physical owned-slot
ledger. Nexus now stores the identity it first observes for each reset
generation in `execution_embedded_store_bindings`. Startup validates the same
identity before starting the dispatch pump. A missing previously bound ledger
or a replacement with a different identity blocks recovery. A fresh generation
creates and binds its ledger before admission. Existing execution history with
no physical ledger is not treated as a fresh store. The operator's database
reset retains old bindings but advances the generation and selects a new
physical directory.

The existing startup directory audit and exact occupied-slot attribution
remain active. This checkpoint does not allow a verified frontier to skip the
directory scan, and it does not establish Connector's physical-store binding.
It detects a partial restore in which only the Server database or only the
Core ledger is replaced; restoring both to a matching older snapshot still
requires the later crash/frontier qualification.

Source evidence: 17 focused cases passed in 305.88 seconds with Core M4d4c1,
including fresh/missing/replaced ledger, bounded historical lookup (1,000
synthetic sessions), exact occupied-slot attribution, three real composition
adapters and initial-refusal restart. The earlier full catalog suite exposed two
obsolete fixture methods when the new identity query was added; the fixture was
updated, and the focused cases passed. The 100,000-session pre-change catalog
run passed before the fixture update; this is not yet a post-change 100,000
session result.

Nexus wheel `0.3.1` SHA-256
`727d5885a8590019ec0eb068e8059ab25937d276479cd66c0b34923bb9776fa1`
and Core wheel `0.0.12` SHA-256
`1d5bdb7a510ad0ad1b8767a156ed3d8c7a042425809227217c0dd46d1eb294ae`
were installed in the disposable Python environment. All 573 Nexus and 162
Core package files matched their wheel contents byte for byte, including the
new migration. The selected installed campaign passed the same 17 cases in
386.02 seconds (`build/m4d4c2-installed.xml`). The global Nexus installation
was not changed.

Both preserved-agent reset variants passed against the installed wheel in
71.94 seconds (`build/m4d4c2-reset.xml`). They confirm that generation zero's
identity remains in the Server database and generation one's identity is new,
while configuration survives and a new message is delivered after reset. An
initial test expectation incorrectly required the bindings table to remain
byte-identical; it was corrected to assert preservation plus one new row. No
production-code change was needed after that result.

The installed cold backup/restore case passed in 43.50 seconds
(`build/m4d4c2-restore.xml`), confirming that a reset-generation snapshot
recovers with its matching ledger. In total, 20 selected installed cases passed.

Remaining M4 work: Connector cross-store binding, audit frontier and crash
matrix, combined metadata budget, scan-cap removal, stream fairness, controlled
real-history latency and the major real Nexus UI gate. The 100,000-session
post-change measurement remains pending. No production rollout or compatibility
claim is made by this checkpoint.
