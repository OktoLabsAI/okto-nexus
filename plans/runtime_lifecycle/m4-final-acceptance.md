# M4 final acceptance — incremental recovery and stream fairness

M4a–M4c replaced broad session-history lookups with exact release queries,
pending projections, and durable release proof. The later Core and Connector
checkpoints M4d4h–m index pending claims, retire accepted terminal streams,
resume older resolved-release cleanup in bounded 128-row pages, and alternate
replay pages among streams. Their installed tests cover interrupted commits,
retained ACKs, 4,097 releases, and histories of 1k/10k/100k rows. No ACK is
advanced past durable acceptance, and a failing stream does not stop another.
The individual measurements and test counts remain in the milestone ledger.

The [physical directory audit](m4n-retained-directory-latency.md) still scans
retained file names at admission to detect unowned files created while Nexus
was down. At 1k/10k/100k files it took 0.092/0.991/9.798 seconds in the
installed local benchmark. That known linear fence is distinct from the
indexed reconciliation of pending claims/releases; this acceptance does not
claim constant-time physical admission. The [local Connector UI gate](m4l-ui-recovery.md)
showed remote Pi delivery before and after a Nexus-only restart and automatic
Connector rejoin. The final [global CI-wheel rollout](m8-global-ci-wheel-rollout.md)
preserved schema 152 and history, recovered local agents, delivered an exact
Pi turn with 1/1 ACK, and retired its consumed session without an orphan
native process.

Core CI 39336889894 and Connector CI 39343006146 each passed 8/8 jobs; Nexus
installed CI 39472894540 passed 24/24. This closes M4's local acceptance
with the physical audit cost explicitly retained. The real Connector test used
another process on this host, not a separate physical machine.
