# Trust and retained recovery regression — October 2, 2026

Five additional findings from the failed full Linux regression are addressed by
current composition/transport tests. Application behavior and the installed wheel
are unchanged from [surface 64](M13_CI_SURFACE_REPAIR.md).

## Findings and corrections

The three presence/trust failures reproduce locally. The tool fixture omitted
`RuntimeAdmissionFence`, which the real bootstrap already supplies. Handoff
composition failed immediately; inbox ACK failed when it lazily composed the same
service. The fixture now supplies the real fence. Existing authentication,
forged-secret, rollback and unread-preservation assertions remain intact.
The complete source module passed 28 tests after correction.

Constructor-time endpoint revocation correctly reaches the constructor and then
fails the current start authorization with HTTP 403/PERMISSION_DENIED. The old
test expected a later 409 revision conflict. The corrected test explicitly proves
one construction, no native start and no persisted harness session, in addition
to checking the refusal. No authorization gate was changed.

The retained handoff recovery test now verifies that the retired stdio entry point
refuses execution. It then recovers through authenticated MCP HTTP and repeats
the same decision through REST. The owner ID/epoch remain unchanged, both results
match and the native send count remains exactly one. This covers retained legacy
work recovery; it does not qualify a new R4 provider journey.

## Installed evidence

The existing surface-64 Nexus wheel was reused (SHA-256
`a6f3edf88fc752e1065c2a58f2caa9daa02926b59a202dfc41c4098acedfec8c`).
Two Windows/Python 3.13.1 campaigns verified all installed Nexus/Core/Connector
bytes against their wheels and ended with unchanged monitored inputs:

- Presence and session recovery: **32 passed in 27.38 s**;
  [campaign](evidence/ci-trust-recovery/trust/campaign.json),
  [JUnit](evidence/ci-trust-recovery/trust/tests.xml).
- Full retained handoff recovery module: **14 passed in 75.25 s**;
  [campaign](evidence/ci-trust-recovery/handoff/campaign.json),
  [JUnit](evidence/ci-trust-recovery/handoff/tests.xml).

Original local failures remain under `evidence/ci-trust-recovery/`.

## CI and remaining scope

The historical Linux/Python 3.13 job at `0e9274b` finished with **42 failures,
3462 passes and 55 skips**, unlike Python 3.12's 43 failures plus one teardown
error. [Recorded job evidence](evidence/ci-trust-recovery/ci-linux313.json)
retains the failed nodes and raw-log hash. The overall matrix was still running
at inspection. Neither job tested these corrections.

NS14 load passed in that 3.13 job but lost WSS during a heartbeat write in 3.12:
the SQLite transaction acquisition exceeded its existing busy timeout. The test
performs 500 authenticated lookups/touches per write transaction under tracemalloc.
Whether batching/starvation or a product load-handling defect caused the failure
still requires controlled diagnosis; neither budgets nor load assertions changed.

Other positive stdio tests, retired native-constructor/multiplex expectations,
complete hosted regression, first-use dashboard/runtime flows, final M13 packages,
independent-host/platform/provider acceptance and G0–G3 remain open.
