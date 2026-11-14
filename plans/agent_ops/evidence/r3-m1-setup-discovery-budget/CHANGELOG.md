# Setup journal discovery budget correction

This new offline candidate derives from the immutable read250 freeze
`d22afc44b0776b3f34429c59d311c85c53d19f7d15ab5d5d7a96135947d333f0`.
Only `controller/setup_journal.py` changes runtime behavior. The original bundle,
v11 campaign, authorization, accounting and checkpoints remain unchanged.

The setup poll previously charged path discovery to a second whole-poll250ms
timer labelled `snapshot_read`, even when no journal existed and no SQLite
operation ran. It now leaves discovery under the existing aggregate poll budget.
`ReadOnly.open` still enforces schema initialization250ms and snapshot250ms,
including cached identity, SQL, projection and rollback. Aggregate600ms,
freshness1s and productive deadline120s remain unchanged. No path checks are
removed, no absent-directory result is cached, and no failure grants a retry.

The final installed-package suite ran once:73 passed and1 explicitly deselected.
This comprises63 prior fixture cases and10 new deterministic cases. The excluded
case reads a real v10 database; it was not needed for this change and was not run.
New cases cover317ms and599ms discovery without SQL,601ms aggregate refusal,
251ms SQL/schema refusal, changed owner identity, symlink/junction refusal, and
controller freshness/accounting/normal-stop behavior. Offline tests are not a
new M1 execution or a real-time operating-system guarantee.

`qualification/v11-diagnosis-final.json` contains only a closed projection of the
failed real v11 campaign, public-evidence/source hashes, readonly SQL queries,
chronology, established causes and explicit uncertainties. The earlier diagnosis
is retained as history. Neither JSON contains database copies, transcripts,
provider configuration, personal authorization material or raw credentials.

The first recorded fault was `SETUP_READ_BUDGET_EXCEEDED`317.696ms against250ms;
the controller selected `OBSERVATION_UNKNOWN` and normal stop. A selected-version
observation0.157.0 was subsequently committed, while the last published inventory
remained `NOT_PROBED`. `INSTALLATION_UNCONFIRMED` therefore describes a missing
ready publication, not proof that the version subprocess failed. The exact cause
of the approximately76-second version-observation delay remains unestablished.
Seven cumulative reservations and89473 observed tokens remain historical facts;
zero newly observed tokens does not establish zero billing.

Final runner uses the exact installed v11 Python with `-I -B`, disables pytest
plugin autoload, and explicitly inserts this candidate's source paths. Its module
origin and pre-run source manifests are retained. No tests should be repeated
without a new change or unresolved failure.
