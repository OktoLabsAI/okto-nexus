# TR4-14-04 combined load acceptance

The normative load entry is now executable as
tests/execution_r4/test_ns14.py::test_ns14_04[load].
The installed campaign passed 47 tests: this scenario plus the affected lease,
opening-bootstrap and native-decision fixtures. All three package trees were
compared against their source and wheel bytes before execution. Product packages
are unchanged from the capacity-metrics increment.

## Workload and observations

One real migrated SQLite store holds 100,000 synthetic offline identities.
Authentication resolves all identities with the real repository and bounded cache.
The indexed lookup plan is recorded; the final cache contains 4,096 entries.
Four retained-memory samples from 25k to 100k lookups remain approximately
3.75–3.78 MB under tracemalloc. The run records CPU, OS, thread bound and timings.
Offline identities do not represent concurrently running provider sessions.

Two separately registered remote executors negotiate real public WSS authority.
The test seeds approved selection metadata and qualifies the technical contract.
It fills the first executor's pending regular budget (32), retains all send ACKs,
and waits for its dispatch regular budget (4) to be occupied. Two real dispatch
pumps share the database. Their transport sinks record authorized frames without
executing a native provider.

A second agent on the second executor sends its opening despite the first
executor's saturation. The first executor sends runtime.close through reserved
control capacity while 20 more productive admissions return 429. Distinct
operation IDs prove no repeated frame emission in this run. Public operator
metrics report 33 pending regular items across the two executors, five held
regular sends and one held control. The original fixture opening accounts for
one held send that predates the two measured pumps.

Final observations on this Windows machine: 29.307 seconds for 100k measured
lookups, 0.276 seconds to emit control, and 0.104 seconds for the second executor.
These are measured results, not latency guarantees. Identity churn precedes the
two-executor queue phase in the same store.

## Failed preparations retained

The initial attempt received an ineligible-intent response after the original
socket was left idle through identity preparation. Later revisions send real
heartbeats while preparing and looking up identities; the reader timeout is
unchanged.

The heartbeat attempt reached dispatch but expected quota refusal after a
one-execution fixture grant had been consumed. The real dispatcher correctly
rejected the next unauthorized send and released its pending charge. This load
scenario now issues a 100-execution grant through the existing authority fixture.

An intervening run held one write transaction while inserting all 100k rows.
SQLite's real busy timeout expired, and the socket closed. Preparation now commits
batches of 500 and yields between batches. No storage or authorization limit was
relaxed. The final campaign completed normally.

Two failed preparation processes remained in TestClient.wait_shutdown. Their
stacks and explicit termination records are retained; only the identified owned
test processes were terminated. Those runs do not qualify successful shutdown.
The initial XML, budget failure/error XML and final XML remain distinct. The
earlier single passing batched test overlaps the final campaign and is not added
to its 47-test count.

## Acceptance scope

TR4-14-04 passes at its specified synthetic load layer: indexed identity lookup,
bounded memory/cache, pending and send quotas, control reserve and progress of a
second executor, with hardware and measurements recorded. NS14.04's broader
dependency acceptance and M11 remain partial. This scenario supplies no native
provider, multi-host, UI, sustained throughput or platform-containment acceptance.
The existing Pi/Codex/Claude and Windows/Linux qualification rows remain in the
fixed delivery plan. G0–G3 remain open.
