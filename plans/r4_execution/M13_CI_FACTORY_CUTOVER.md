# Native factory cutover and canonical reuse — October 2, 2026

Nine historical CI failures expected the removed Server-native constructors to
launch Codex through legacy endpoints. Production correctly returns migration
required: native execution moved to Core in NS15.03. Restoring those constructors
or injecting adapters while continuing to call the tests production acceptance
would contradict the cutover.

The old pool tests now verify the actual production boundary: approved legacy
profiles cannot launch a runtime, even with identical profiles, concurrent opens,
or changes to agent, workspace, profile ID/revision, resolved secret or HITL.
They assert explicit migration refusal and no live/persisted harness session.
They no longer claim production pooling or qualify a Core provider.

Canonical R4 coverage now submits two competing automatic starts concurrently
through public HTTP, proving one admission and one refusal with one native opening.
A new explicit-session lifecycle check opens two synthetic Core peers, closes one,
sends a turn through its surviving sibling, then closes the sibling. Native instance,
stop and send assertions demonstrate isolation without claiming process pooling.
The reuse fixture verifies real installed protocol readiness instead of overriding it.

The legacy worker-capacity regression explicitly injects the retained Codex test
adapter. Its original blocked-worker/healthy-agent progress assertions remain.
That case covers retained Server worker behavior with a scripted native peer;
it is not acceptance of a current production native constructor.

## Installed evidence

The existing surface-64 wheel was reused, SHA-256
`a6f3edf88fc752e1065c2a58f2caa9daa02926b59a202dfc41c4098acedfec8c`.
Both Windows/Python 3.13.1 campaigns verified Nexus/Core/Connector installed bytes
against their wheels and report unchanged monitored inputs:

- Factory cutover, retained worker and R4 reuse: **23 passed in 100.07 s**.
  [Campaign](evidence/ci-factory-cutover/cutover/campaign.json),
  [JUnit](evidence/ci-factory-cutover/cutover/tests.xml).
- Shared-fixture dependents (NS05.04, admission capacity, initial turns and parent
  loss): **19 passed in 73.12 s**.
  [Campaign](evidence/ci-factory-cutover/reuse-dependents/campaign.json),
  [JUnit](evidence/ci-factory-cutover/reuse-dependents/tests.xml).

## Remaining CI and release work

The historical Linux/Python 3.11 job at `0e9274b` finished with 44 failures,
3460 passes and 55 skips; the overall matrix was still running at inspection.
[Job evidence](evidence/ci-factory-cutover/ci-linux311.json) records its failures
and log hash. Compared with Python 3.13, two additional failures need diagnosis:
missing-provider-credential refusal was obscured by a later shutdown error, and
the 100 ms global boot-budget fixture did not reach native startup. Neither is
declared fixed by this increment. NS14 SQLite contention also remains unresolved.

Current full hosted regression, final immutable packages, complete dashboard flows,
independent hosts and native platform/provider acceptance remain open. No G0–G3
gate closes and these synthetic checks do not replace physical-host acceptance.
