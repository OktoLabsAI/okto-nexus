# M3u — CI consumer alignment

Core CI run `39178772289` reached its Linux, Windows and macOS Intel test
matrices and failed on stale fixtures/documentation plus one missing public
runtime delegation. Core commit `8bde891` fixes the demonstrated causes;
29 focused source tests passed locally, and the new full CI run is
`39180450008` (pending platform qualification at this checkpoint).

Connector CI run `39178834200` used an older vendored Core 0.0.12 wheel.
The missing pending-claim/retirement methods caused repeated daemon recovery
errors. Connector commit `6c8a7c0` synchronizes the rebuilt wheel and adjusts
fixtures for the current schema and independent pending inventory. Its
isolated installation passed 65 recovery/registration cases, 95 related
cases before one cancelled-reader expectation was updated, and that case
passed separately. The new Connector CI run is `39181170027`.

Nexus and Connector now vendor the same rebuilt Core 0.0.12 wheel, SHA-256
`faea17f68891a6112a6392c5b6078ce06583a5e34e718fb152380c92f30bfa64`.
With that wheel installed in a disposable environment, the Nexus startup
session-isolation file passed all 14 cases in 229.26 seconds. The earlier
Nexus run `39178808095` was cancelled because it used the superseded wheel;
the full installed matrix for this exact consumer set remains pending. The
global Nexus instance remains stopped. No current UI availability is claimed.

The first rerun, `39181288320`, stopped in every started shard before tests:
`tools/ci_installed.py` correctly rejected the new Core wheel because
`vendor/ci/manifest.json` still pinned the old SHA. The manifest is now
updated to the exact wheel above and `dependency_wheels()` verifies both
artifacts locally. This is an artifact metadata correction; it does not
change execution code or acceptance criteria.
