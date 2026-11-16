# Installed final Server-attention package

This cut builds from the frozen source at `3d95aad8`, including the separate
Server-attention projection, paging and UI. `qualification.json` records the
actual wheel/sdist hashes, installed test outcomes and input verification.

The finite pipeline makes an isolated source copy, compiles TypeScript/Vite to
that copy, builds wheel/sdist, checks both with Twine, reinstalls only Nexus into
the existing disposable Python313 prefix with `--no-index --no-deps`, and invokes
`ci_installed.py test` with `-I` from an independent cwd. Its probe compares all
three installed distributions against their wheels. Connector is a test-only
dependency; this does not add it to Nexus's runtime dependencies.

The requested focal cut is eleven Server-attention cases plus the packaged Home
resource/HTTP contract. Synthetic valid canonical occurrences exercise the global
query-port contract; they are not evidence of a newly invented global producer.
These tests are SQLite/ASGI/package tests, not a provider campaign, browser
qualification, production deployment or latency/SLO measurement. Existing broader
and earlier installed cuts are retained separately and not added to this count.

Input hashes are captured before the build and compared after installed tests,
covering source, tests, docs and frontend inputs. Plans/Home evidence is excluded
by the existing runner, allowing concurrent ledger/evidence curation without
silently qualifying changing product bytes. Wheel payload/static bytes are also
compared directly to the frozen checkout.

The initial Twine phase failed because the development venv lacks that module.
An existing system Twine executable checked the same already-built artifacts;
no dependency was installed and the build was not restarted. Only after those
checks passed did the original intended Nexus-only reinstall and tests proceed.
`PREPARED.json` is the antecedent preparation record, not the final outcome.

No personal authentication, provider call, native harness executable, operating
system service command or Windows session event is part of this qualification.
The canonical native-question fixture used by one test employs synthetic
admission/ingress and its own in-process test host, not a live provider process.
