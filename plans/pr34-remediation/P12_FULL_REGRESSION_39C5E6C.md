# Full regression before final correction

Windows source39c5e6cc44481467a6785b09e11219f5c57b2f62, handle51046,
terminal exit1: **2630 PASS /5 FAIL /121 SKIP**,2 warnings,3805.65s.
[Per-node manifest](evidence/p12-full-39c5e6c-windows.json) retains exact command,
environment and XML checksum. Raw logs/XML stay private under .git/pr34-evidence.
The main production/tests were unchanged for the whole run; later commits edited
documentation only. This is a failed full gate, not a candidate qualification.

| Failure | Observed terminal assertion | Correction scope |
|---|---|---|
| Claude event iterator | first event0.2139898s exceeded0.2s | Replace startup-sensitive timing proxy with real condition notification and held polling-clock negative control; production connector unchanged |
| Grouped inbox receipt |2 unread notifications instead of1 | Restore ordinary grouped receipts, keeping external operation-specific acknowledgement provenance separate |
| Attempt-history upgrade,2 parameters | actual59..64 versus expected59..61 | Explicit expected migration list updated; additive/backfill/idempotency assertions retained |
| Reconciliation upgrade | actual54..64 versus expected54..61 | Explicit expected migration list updated; retained data and repeated-apply assertions unchanged |

The terminal Claude trace confirms the tight latency assertion failed; it does not
prove polling occurred. The independent delayed-fixture counterexample and
mechanistic replacement are documented in
[P12_RECEIPT_GROUPING_REGRESSION.md](P12_RECEIPT_GROUPING_REGRESSION.md).
That document also records isolated RED/green results for all five candidate paths.
Those paths are not yet transferred to main while the Linux full run remains live.

Linux sourcee44d230fb74be2dc552659642226e84aeb62affc has identical production/tests;
handle29628 remains running. Await its terminal result before integration. Both
platforms used distinct fixture stores; their durations overlap and are not
performance measurements. Installed providers and UI were explicitly disabled;
SKIP is not PASS. No native campaign or final release result follows from this run.

## Linux terminal result

Handle29628 completed exit1:2708 PASS/4 FAIL/44 SKIP,2 warnings and2 passed
subtests,4735.30s. The four failures are the grouped receipt assertion and the
three stale migration-list assertions already reproduced in isolation. The old
Claude timing test passed on Linux. This does not negate its Windows failure.
[Linux per-node manifest](evidence/p12-full-e44d230-linux.json) records the real
launch SHAe44d230 and implementation equivalence to39c5e6c. Both old-source runs
are now terminal, so main integration may proceed. Full corrected Windows49697
is running separately against the frozen five-path candidate.
