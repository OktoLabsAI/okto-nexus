# SI-039 installed migration and historical receipts

The Nexus 0.3.8 wheel, installed with Connector 0.0.15 and Core 0.0.16,
migrated three disposable copies of databases from previous native Codex and
Pi probes on Windows. The current main refs were fetched before the check.
Exact package hashes, inspected refs and hashes of the preserved records are
in the [migration evidence](si039-installed-migration.json).

| Historical copy | Schema | Preserved receipts | Additional evidence |
| --- | --- | ---: | --- |
| Codex after saved-context recovery | 182 → 187 | 4 | Previously verified saved contexts retain their original witness and release digest. The new adapter column identifies them as `codex_app_server`. |
| Pi with a queued input | 186 → 187 | 2 | The active session keeps its queued input and canonical receipt. |
| Pi after native acceptance and close | 186 → 187 | 6 | The closed session keeps its native acceptance and canonical receipt. |

The Nexus migration runner read only the copied databases. Each comparison
covered the original columns of receipts, operations, results, session and
runtime event data, and any input and queue tables present in the source.
The checks compared canonical frames and stored digests along with the other
legacy values. Each schema passed SQLite integrity and foreign-key checks.
Reapplying the migration runner applied zero migrations in all three copies,
and the original snapshots remained identical.

The migration and queue storage suites passed 20 tests with the installed
candidate. They covered transaction rollback, concurrent bootstrap and the
retired-session migration that blocks unsent input while preserving its
receipt. The historical databases came from native runtime tests with
deterministic peers. SI-T-I01 has evidence at the integration and installed
package layers. Its campaign layer and the remaining SI-039 compatibility
gates are pending.

This evidence increment has no code, pin or migration change. Reverting the
evidence commit removes its ledger entries and reports. The disposable copies
can be recreated from the previous snapshots without rolling back schema in
place.
