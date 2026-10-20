# M4d4f2: reject non-files during the physical admission audit

`EmbeddedSessionCatalog.audit_files()` previously checked each directory
entry's name against the canonical Server catalog. A directory or symbolic
link with a registered journal name could pass that name check. The startup
audit now requires each scanned entry to be a regular file without following
links. A failed type check retains the existing `JOURNAL_UNAVAILABLE` fence;
it does not infer an empty store or release capacity. The check applies to
the owned-slot ledger, journals and their sidecars.

The focused source campaign passed three cases: registered journal/ledger
directories and unknown names are rejected; a missing ledger is rejected;
and a fresh store binds its ledger before admission. The same three cases
passed from a Nexus 0.3.1 wheel installed alongside the exact vendored Core
0.0.12 wheel in a separate virtual environment. Nexus and Core imports were
verified under that environment's `site-packages`. The Nexus wheel SHA-256 is
`07adb89886c0a8ba2914b446540006ea8cf4798c1b5d64f4b8238acf3e67d4f4`.
The test environment reused already installed third-party dependencies; it
was not a clean dependency-resolution campaign.

A disposable 10,000-file source-tuple benchmark measured 0.997 s for the
audit, 79 batches of at most 128 names and 152,606 SQLite VM steps. Its
fixture setup took 17.285 s. The prior 10,000-file measurement was 1.634 s;
different machine load prevents attributing that difference to this change.
No real harness or global Nexus process was used.

This validates entry type at scan time. It does not prove the directory was
unchanged while the service was stopped or prevent a later filesystem race.
The complete physical name scan remains on the admission path. The M4
retained-history, mixed-capacity, stream-fairness and real UI gates remain
open; no global rollout is claimed.
