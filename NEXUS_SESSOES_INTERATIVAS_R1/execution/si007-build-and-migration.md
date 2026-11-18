# SI-007 Windows build and migration boundary

The Nexus 0.3.8 wheel and source distribution built offline and passed
Twine strict checks. The wheel contains the exact source bytes of all
five interaction migrations and four application modules checked in this
run. Wheel SHA256 is
`4306df83626967bbc02228de22de2298f0a1f52fe453f42c4e9285ba8585d07d`.

An isolated database from the installed Nexus 0.3.7 upgraded from schema
168 to 173 using the built 0.3.8 wheel. The Server identity, fixture agent,
existing operator login and foreign key consistency were preserved. The
existing login received a revocable authority reference in the new build.
The 0.3.7 guard refused schema 173. It reopened the separate pre-migration
copy at schema 168 with the original data and login.

Rollback of behavior after accepting queue data requires a schema-aware
build and reconciliation of every in-flight operation. Reopening a backup
is proof of pre-migration recovery only. Migration history and newer
receipts should remain available. The user's installation remains on
0.3.7. The upgrade and recovery used disposable data.

The latest interaction/R4 regression passed 83 tests. The migration
suite passed seven tests. The separate import boundary check reported two
pre-existing `sqlite3` imports in `application/home.py` and
`application/connection_public_ids.py`. Both files match the branch
baseline. Native harness and user-surface qualification are still pending.
