# Independent HTTP clients and store writers — October 2, 2026

Seven remaining full-CI failures attempted positive execution through retired
stdio. Those cases now test their actual invariants without restoring stdio.

## Transport and persistence scope

`runtime_http_client.py` starts an isolated interpreter in the disposable project,
initializes the MCP SDK over authenticated HTTP and invokes the requested tool.
It receives credentials over stdin and never composes Nexus or Core; absence of
all three application packages from its loaded modules is asserted. Existing
outbox tests verify dispatch by the active serve owner and session creation in
that owner's supervisor. Quota/fsync capture faults are tested through this
independent client as well as direct MCP HTTP and REST commands; assertions retain
zero new commands, messages, results, outbox rows or native sends after refusal.

Writer compatibility needs a separate invariant: a process touching an already
active store must obey its writer contract even with stale feature flags.
`runtime_writer_process.py` is explicitly a **test-only application writer**, not
a transport or supported CLI. It uses installed bootstrap, authenticates the
disposable caller and invokes the real message use case without starting an owner.
Tests retain incompatible-writer refusal/rollback, atomic operator disable,
compatible canonical enqueue and operator-only diagnostics. Migration rollback
now reads SQL from the installed package instead of checkout source.

## Installed verification

The old temporary environment became incomplete before validation: `jsonschema`
could not import, and `uv pip check` found 42 broken/incompatible entries. No cause
is inferred. A new environment outside Windows Temp was created with Python 3.13.1
and copy-mode installation from the existing Nexus/Core/Connector wheels.
All 47 installed dependencies pass `uv pip check`; their inventory is
[recorded](evidence/ci-http-clients/dependencies.json).

The Nexus wheel is unchanged from surface 64, SHA-256
`a6f3edf88fc752e1065c2a58f2caa9daa02926b59a202dfc41c4098acedfec8c`.
Both passing campaigns verify installed application bytes against all three
wheels, run outside the checkout and report unchanged monitored inputs:

- HTTP process clients and complete capture-admission module: **11 passed in
  68.24 s**. [Campaign](evidence/ci-http-clients/http/campaign.json),
  [JUnit](evidence/ci-http-clients/http/tests.xml).
- Complete writer-contract module: **7 passed in 24.64 s**.
  [Campaign](evidence/ci-http-clients/writer-corrected/campaign.json),
  [JUnit](evidence/ci-http-clients/writer-corrected/tests.xml).

The initial writer run (three failures, four passes) is retained. Its test helper
assumed an unstarted dispatcher existed as an explicit `None` attribute; the
assertion now also accepts the actual bootstrap's absent attribute. No product
behavior was changed. An earlier collection attempt ran no tests because editing
had failed before the new node names existed; it provides no acceptance evidence.

These are synthetic-peer loopback and store-compatibility checks, not independent
physical hosts or full R4 native-provider acceptance. Retired production factory
expectations, NS14 load contention, full current CI, dashboard completion, final
artifact freeze and G0–G3 remain open.
