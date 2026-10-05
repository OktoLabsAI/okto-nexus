# Canonical method denials during legacy migration

The migrate-execution command now includes legacy connection-method rows in its
bounded batches. A denied legacy method creates the corresponding canonical
agent_connection_methods row with enabled=0, preserving the original row.
The existing binding prepare/apply policy guard therefore reads the denial using
the canonical adapter ID. The migration translation table remains outside the
runtime path.

Source allows do not create canonical allows or grants. An existing canonical
denial is preserved. A legacy denial conflicting with an existing canonical
allow refuses the transaction and requires explicit policy review; neither row
is silently changed. A migrated denial that later disappears or becomes enabled
also prevents migration continuation.

Policy map entries record source digests, canonical method, whether a denial was
added and the batch ID. Baseline comparisons exclude only canonical denial rows
explicitly added by this migration, and those generated rows are checked as
denied before each resumed batch. Original policy rows remain in the baseline
comparison. The same batch-size ceiling includes policy and catalog records.

The command requires no live legacy dispatcher lease, checked before schema
expansion and again inside the batch transaction. Stop/drain the runtime owner,
then take the original migration backup and keep that backup for all resumed
batches. This check does not claim to contain orphaned processes or complete M4.

## Verification

The installed campaign passes 11 migration/backup cases and 40 admin/architecture
regressions. The new cases prove the canonical binding guard refuses the
materialized denial, conflict leaves policies and maps unchanged, modified
generated policy prevents continuation, and a live runtime owner prevents schema
expansion and policy writes. The injected transaction failure still rolls back
policy and map writes together. The initial live-owner fixture used positional
values against a six-column table; that failure is retained and the fixture now
names its four intended columns.

Nexus source/wheel/installed bytes were compared before the run. Core and Connector
artifacts remain unchanged. Earlier source runs overlap the 51 installed cases.

## Remaining scope

M3 endpoint adoption still needs reviewed rediscovery, preserved endpoint identity
and consent. Full TR4-15-01, runtime cutover, rollback, providers/platforms and
release gates remain open. This increment fixes policy linkage only and does not
activate executable bindings.
