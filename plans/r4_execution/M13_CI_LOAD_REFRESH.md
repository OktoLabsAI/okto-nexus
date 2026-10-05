# Windows CI follow-up — October 2, 2026

Historical run 36966572607 is terminal. Windows/Python 3.11 reported 45 failures,
3385 passes and 129 skips; Windows/Python 3.13 reported 44 failures, 3386 passes
and 129 skips. Both cells rejected the NS14 load campaign with
`inventory_not_fresh`. The fixture did not renew its initial observation after
100,000 identity lookups, which can exceed the 120 s freshness window.

The fixture now fingerprints the candidate again, constructs a new Core snapshot
with the next publication sequence and publishes through the HTTP API using the
ticket and producer identity of the reconciled control channel. It verifies the
unchanged inventory revision and positive freshness. The second synthetic
executor starts with a consistent sequence of one. Product freshness and
authorization rules, quotas and measurement thresholds are unchanged.

The Pi technical-host test previously requested native-action shutdown with the
default zero wait, ignored its completion result and immediately asserted that
the TCP listener was closed. It now waits up to five seconds and requires a true
completion result before testing connection refusal. Pending-producer/storage
assertions remain intact; no product shutdown behavior was changed.

## Verification

The corrected load scenario passed in source in 91.05 s. All four technical Pi
cases also passed. The first two load fixture attempts failed at ticket scope
and current-channel validation, respectively; their reports are retained and
are not counted as passing acceptance.

Installed Windows/Python 3.13.1 verification passed **six tests in 147.08 s**:
the 100k load scenario, four technical Pi cases and the inventory HTTP authority
test, including the refusal to refresh freshness through replay. Inputs were
unchanged and all three installed packages matched their pinned wheels.

- [Campaign](evidence/ci-load-refresh/campaign.json)
- [Installed package hashes](evidence/ci-load-refresh/installed.json)
- [JUnit and recorded load metrics](evidence/ci-load-refresh/tests.xml)
- [Historical Windows 3.11 findings](evidence/ci-load-refresh/ci-windows311.json)
- [Historical Windows 3.13 findings](evidence/ci-load-refresh/ci-windows313.json)

This campaign uses synthetic inventory, transport sinks and a technical Pi child.
It does not qualify a provider release or independent physical hosts. The Nexus
wheel remains `d28a7a22cfa167a9598688fc7a31ace8e28eb484b5a901c6ff37be8b67dc6e91`;
no application package was changed by this increment.

## Open findings

Linux/Python 3.12 NS14 SQLite contention and the Windows native-capture test
(199/203 journal records observed before its eight-second deadline) remain
unresolved. The capture observation alone does not establish whether projection
blocked ingress or capture was slower than the fixture expected.

Connector HEAD `e09fa21` CI run 36969483960 is also terminal: five platform/Python
cells passed, Windows/Python 3.13 failed one test
(`test_default_daemon_publishes_retained_observation_without_probing`, TimeoutError;
698 passed and two skipped), and build was skipped. Core HEAD `3a1e884` run
36961433275 succeeded. Current full Nexus CI, Connector timeout diagnosis, final
artifacts, UI completion, NS15.05 reconciliation, independent-host acceptance and
G0–G3 remain open.
