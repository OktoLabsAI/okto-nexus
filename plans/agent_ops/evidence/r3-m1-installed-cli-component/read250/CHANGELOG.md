# Observer read budget: 100 ms → 250 ms

This candidate changes only the local observation budget and its reported
metadata. The preceding CLI candidate remains frozen at
`167f5f3f1e62dad1db0018afe23eb174f9d36a10ef5ce677ef92a4e2b14312b3`.

The preceding complete offline suite retained two failures: a Core snapshot
took 211.2865 ms in the global-ledger fixture, and another took 153.5869 ms in
the four-work CLI composition. Both exceeded the former 100 ms budget and
correctly closed the reader and effect fence. Those failures are preserved;
this calibration does not relabel them as passes.

`ReadOnly` now defaults to a 250 ms observation budget and permits explicit
values up to 250 ms. Public Canonical/Core reads and setup observations include
path/identity checks, projection and rollback. Separately measured schema
initialization still has its existing 250 ms budget. SQLite connection/busy
timeouts derive from the local read budget, so their default also becomes
250 ms. Explicit 100 ms and 40 ms overrides remain supported and tested.

The aggregate poll budget stays at **600 ms**. It includes initialization,
observations and normal controller persistence. Progress callbacks and checks
after I/O still enforce the remaining aggregate budget. Thus an individual
read may consume more of the same poll allowance; multiple 250 ms reads do
not obtain independent 600 ms allowances.

Effect-observation freshness remains **1 second**, the request deadline
**120 seconds**, preventive cumulative usage **200,000 tokens**, operational
tolerance **700,000 tokens**, and admission limits **5 new / 11 cumulative**
with **6 admissions and 89,473 tokens carried in**. No persistence redesign,
deduplication, polling-loop change, PTY cadence change, product modification,
provider invocation or service action is included.

The previously observed `maximum_previous_poll_ms = 740.4216` measures the
whole poll, including fault persistence and containment after its fence has
closed. The retained case already had a 153.5869 ms read refusal and did not
publish useful success. It is therefore not evidence of an accepted 740 ms
cycle. The old report does not separate cleanup timing, so it also cannot
prove how much of those 740 ms was cleanup. Normal completion checks the
600 ms budget again after its final durable I/O. OS I/O and scheduling cannot
be preempted; these remain fail-closed acceptance budgets, not hard physical
wall-time guarantees.

Tests preserving the old 100 ms boundary now specify that override explicitly.
A deterministic default-budget case accepts 211 ms and rejects 251 ms. One
complete final suite is run on pinned candidate bytes; any failure is retained
without repeating the suite until green.

This is an offline harness calibration. The proposal must explicitly replace
its 100 ms read metadata with 250 ms while retaining all global limits. Root
approval of preparation and authorization of real M1 execution remain distinct;
this candidate does not authorize or prove real M1 acceptance.
