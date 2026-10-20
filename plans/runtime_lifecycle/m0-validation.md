# M0 validation — 2026-10-16

The baseline preserves the changes already developed and installed before the
runtime lifecycle plan. It is not a claim that startup recovery is solved.

- Prior installed event-artifact campaign: Core 24, Connector 41, Nexus 41 passed.
  Details and limitations: `../event-artifact-implementation.md`.
- Current Nexus source regression gate: **25 passed**, covering released closes,
  partial-result presentation and retryable dispatch database contention.
  Command: isolated Python with `src` on the path, `pytest -q
  tests/test_released_closes.py tests/test_runtime_result_presentation.py
  tests/execution_r4/test_dispatch_pump.py`.
  Local JUnit evidence: `build/runtime-lifecycle-m0.xml`.
- Previous frontend production build and UI checks are recorded in
  `../settings-and-dispatch-contention.md`. No new UI behavior changed in M0.
- Checked project versions, dependency pins and metadata of vendored Core and
  Connector wheels. Both consumers require Core 0.0.12.
- Credential-pattern scan of changed/new text files found no supplied tokens.
- Core/Connector whitespace checks passed. Normalized generated Nexus HTML line
  endings; content and referenced production assets remain the same.

One existing Starlette/httpx deprecation warning was emitted by the test client.
The running Nexus instance was not restarted or changed for these validations.
