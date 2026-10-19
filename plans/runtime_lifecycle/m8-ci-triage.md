# M8 installed CI triage (2026-10-19)

The baseline Nexus run `39181558602` was cancelled after Ubuntu 3.12 and
3.13 shard 0 failed. Ubuntu 3.12 shard 0 reported 41 failures, six errors,
1043 passes and 26 skips. No final Nexus matrix pass is claimed.

Closed findings in this checkpoint, with focused installed Windows tests:

- Session isolation changed a failed opening from agent-wide blocking to
  session-scoped recovery. The eight interrupted preopen tests and the
  canonical boot and vault failure checks now assert the contained session.
  All 11 preopen cases, plus both canonical checks, passed locally.
- The independent inventory observer now derives discoverable runtimes from
  the Core catalog. The registered-adapter fixture needs an executable name;
  the old directory-absence assertions and immediate inventory read were
  obsolete. Five registered-adapter tests and four inventory, realization and
  shutdown checks passed locally.
- Retirement can run independently of asynchronous inventory freshness. The
  test now waits for the adapter's usable observation before sending new work.
  Its three adapter cases and other maintenance cases passed locally.
- The migration fixture must remove newer views before simulating schema 96,
  then restore them after applying migration 96. Its focused test passed.
  The history migration assertion was updated to current schema 152.
- The one-slot handoff fixture was changing only the host field after the
  durable capacity ledger had already initialized to 64. It now sets both
  test capacity facts to one; the real concurrent reservation test passed.
- The runtime-options test no longer monkeypatches the shared platform probe
  while the independent inventory observer can legitimately run it.
- A renewal denial claims one retirement checkpoint revision when it records
  the containment obligation. The four commit-cut assertions now require that
  exact increment while still rejecting any physical release; all four passed
  locally.
- A registered, rootless workspace can now upload managed artifacts. The
  focused HTTP test and real UI upload/send/read passed.

Open Nexus CI groups from the cancelled run: Linux subprocess Connector
startup in remote handoff/containment cases and remaining shard results. The
same remote cold-start and preopen cases passed on installed Windows. The
subprocess fixture now includes its stderr
on failure so the next Linux run can identify the root cause. Treat failures
as open until rerun; do not infer a full pass from Windows focused tests.

Core `39180450008` passed, including SBOM. Connector `39183939833` passed
Linux/macOS but had one failure each on Windows 3.12 (an inventory startup
attempt did not begin before its 15-second deadline, with a transient
`RUNTIME_DRAINING` startup log) and 3.13 (a native claim committed before the
socket closed). The latter test now accepts either settled race outcome and
checks any success reply against the committed effect; its focused tests pass
on Windows. Connector matrix rerun remains pending.
