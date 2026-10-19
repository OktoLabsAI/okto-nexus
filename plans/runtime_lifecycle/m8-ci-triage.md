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

The isolated Ubuntu 3.12 shard-0 rerun of `39190838641` failed 27 cases and
passed 1164. Its remote Connector subprocess failed at import time because
the Nexus CI vendor wheel omitted `R4Connection.publish_startup_refusal`,
which exists in current Connector source. The vendor wheel and manifest now
contain the current Connector 0.0.10 build; its installed remote handoff case
and vendor integrity tests passed locally. This accounts for 11 failures.

The remaining failures exposed three bounded issues: the handoff compensation
writer used `CANCELLED_NO_EFFECT` for an attempt with a committed operation,
while schema 151 requires `FAILED_NO_EFFECT` (four cases); a capacity recovery
fixture omitted `deps` (two cases); and tests sent new work immediately after
restart before asynchronous inventory publication (nine cases). Those cases
now await observation. The dispatch pump also retains pending work while the
new owner's inventory publication is absent, instead of recording a terminal
conflict. All 29 local installed recovery/compensation cases passed, including
the pending-work restart case. A new full Nexus matrix is still required.

Core `39180450008` passed, including SBOM. Connector `39195567707` passed
Linux, macOS, Windows 3.11 and 3.12. Windows 3.13 alone timed out in a
15-second test watchdog waiting for four concurrent cold openings; the same
three test variants and full 22-test module pass locally. The watchdog now
allows 30 seconds for hosted-runner durable journal I/O. A full Connector
matrix rerun is still required.
