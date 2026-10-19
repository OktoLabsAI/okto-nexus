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

The next installed Nexus matrix, `39198137896`, was cancelled after its first
Ubuntu 3.11–3.13 shards reproduced four bounded findings. Remote reconnect
replay called `is_attached` on the recovery channel, which did not implement
the regular connection's method; Connector `748c0ba` adds it. The Nexus CI
vendor wheel now contains that exact Connector build. Existing tests also
needed to wait for accepted inventory after remote startup, use the current
session-scoped containment result, and compare the current schema 152 and
executor snapshot format 3. The affected local installed cases passed,
including seven deadline/restart/expiry variants and two startup-refusal
variants. These are checkpoint results, not a final matrix pass.

Connector `39203007257` subsequently failed one Windows 3.11 capacity-wait
case after 1203 passes: four concurrent turns contended for the publication
store's writer lock until SQLite's 10-second timeout. The store acquired
`BEGIN IMMEDIATE` and repeated schema DDL for every read. Connector `8310f9b`
initializes the schema once per store instance and uses read transactions for
queries, retaining immediate transactions for mutations. The installed
capacity-wait and publication modules passed 29 cases locally. Its replacement
matrix is `39204601574`. The Nexus CI vendor wheel was rebuilt from that
Connector commit (SHA-256 `562dd5e174a6a974440a28038cd2a10e4d103772d609d8dc512e58fb8e20fa0c`).
The rebuilt wheel also passed the seven Nexus vendor-integrity cases and
three real Connector process/restart capacity cases in the isolated installed
environment.

Connector matrix `39204601574` passed all eight jobs, including the six
installed Linux/Windows Python combinations, macOS daemon, and build. Core
matrix `39180450008` also passed. Nexus matrix `39204884009` remains in
progress on the `78093da` vendor-wheel checkpoint. Its first nine completed
jobs exposed existing tests that raced independent inventory publication or
asserted agent-wide containment after session-scoped recovery. The focused
installed corrections now wait for accepted inventory in remote handoff,
daemon startup, local recovery and isolated recovery fixtures; retry only
typed stale-inventory/generation failures in the CLI and remote preopen
fixtures; and assert the current session-scoped outcome in embedded failure
and NS15 restore tests. The canonical recovery test counts its original
message by identity, since a legitimate asynchronous release notice can add
another message. The session-pagination fixture now gives cloned sessions
distinct journal names. The relevant local installed cases passed, including
the three Windows shard-3 cases. The remaining matrix jobs and a replacement
full Nexus matrix are required before M8 qualification.

Windows 3.13 shard 0 also exposed a real pending-work failure: after restart,
the sender could reserve a retained operation while inventory publication or
binding revalidation was still converging, then terminate the unsent operation
with `inventory_not_fresh`. The sender now releases that exact unsent
reservation back to PENDING for incomplete receipt, observation, or
revalidation and retries after the normal poll. A confirmed incompatible
revalidation remains a terminal denial. Eleven installed dispatch and preopen
recovery cases passed locally, including deterministic transient and confirmed
incompatible paths. The interim matrix `39213179560` was cancelled after this
new product finding; its commit lacked the fix. The first matrix
`39204884009` was cancelled after 12 completed jobs, all of whose failures
were classified, to free runners for the corrected matrix.

The corrected-commit matrix `39214894629` passed Ubuntu 3.13 shard 1 but
Windows 3.13 shard 3 exposed two bounded issues. The compensation test still
expected the old handoff-attempt state `CANCELLED_NO_EFFECT`; the current
schema-151 writer correctly persists `FAILED_NO_EFFECT` for that attempt,
while the admission remains `CANCELLED_NO_EFFECT`. The offline backup checked
the source tree before acquiring its SQLite writer fence and checking the
owner lease, so a Windows `nexus.db-shm` file could disappear during that
precheck. The tree check now runs under the fence after lease validation.
Both affected modules passed 21 installed local tests. The rest of the matrix
is still required; no full Nexus pass is claimed.

Windows 3.13 shard 0 then exposed a canonical identity test still requiring
agent-wide recovery after an uncertain post-spawn failure. The native process
was reaped, the one failed session closed, the agent stayed unblocked, and
the operation retained `OUTCOME_UNKNOWN` without replay; the test now checks
those current guarantees. All eight installed identity cases passed. Ubuntu
3.12 shard 1 exposed an exact replay-count assertion after journal checkpoint
loss. Independent compaction may retire the already projected record before
manual recovery, producing zero replayed records instead of one while the
result remains singular. The test now accepts either bounded replay count and
still checks exactly one durable event and result. All 12 installed journal
cases passed. The matrix remains a triage run pending final rerun.

Windows 3.11 shard 0 exposed two restart-process fixtures publishing a new
local realization with the inventory revision saved by the previous process.
The running owner and independent observer were healthy; the stale selection
was correctly refused. The fixture now waits for accepted inventory from the
replacement owner and uses its current candidate/revision. All three real
process-exit variants (`graceful`, `kill`, and `kill-before-bind`) passed in the
installed local environment. Windows 3.12 shard 0 and Windows 3.11 shard 3
repeated already corrected identity and compensation expectations.

Windows 3.11 shard 2 and Windows 3.12 shard 2 exposed the same remaining
fixture failures. The real-serve setup could race a new independent inventory
publication between selection and realization/binding, so it now retries only
the typed stale-selection conflicts with a fresh snapshot and a new intent.
The startup privacy test still waited for the obsolete agent-wide recovery
row; it now observes the session-specific blocked event for the failed
session. Four privacy variants and the clean signal-drain process case passed
in the local source run. A separate wheel-based run used
`tools/ci_installed.py` with an independent working directory and verified
that Nexus, Core, and Connector were imported from `site-packages`. Across all
five modules using the real-serve fixture, it passed 15 cases, skipped three
POSIX-only cases on Windows, and reported no changed inputs. The rebuilt
Nexus 0.3.1 wheel SHA-256 was
`d4f8f46ebc48c87666cd68f7cbc664fc816497ba8364168491922bfa08955d9c`.
The same installed wheel passed 11 dispatch/independent-boot cases and 41
compensation, offline-backup, canonical-identity, and journal cases, each
with unchanged inputs. Total focused installed result: 67 passed, three
Windows platform skips, zero failures.
The old triage matrix was cancelled after eight classified failures; final
matrix `39230234802` runs against commit `1f2558e`. The full Nexus matrix
has not yet passed.

Ubuntu 3.13 shard 0 of that matrix refused a healthy agent's new opening
immediately after restart. The test had waited only for the current
publication sequence, which does not prove the selected adapter's observation,
binding revalidation, or executor control readiness. The test now waits for
those admission conditions. Both fault variants
(`unavailable` and `hung`) passed locally against the installed Nexus wheel.
The other matrix shards remain in progress; this is not a full-matrix pass.

Matrix `39239613854` on commit `c679603` passed the earlier failing Ubuntu
3.13 shard 0. Windows 3.13 shard 0 then refused a fresh request with the
specific blocker `inventory_not_fresh` in a second interrupted-launch restart
test. That test also waited only for the publication sequence. It now waits
for the selected adapter's fresh observation, accepted binding, and ready
executor before admitting the replacement request. All six interrupted-launch
cuts (`intent`, `effect`, `claim`, `container`, `spawn`, `birth`) passed locally
against the installed wheel. Remaining shards of the matrix are still being
classified before another full run.

Ubuntu 3.11 and 3.13 shard 1 in the same matrix timed out at three hours in
`test_heartbeat_storage_failure_closes_link_and_releases_owner`. Local
reproduction showed the test's failure wrapper also intercepted
`last_seen_at` writes from unrelated executors during `TestClient` startup,
before the remote heartbeat under test. The fixture now arms the failure only
after the remote link's handshake and matches that executor. All three
storage/authority variants passed locally against the installed wheel in
20 seconds. This was a test-injection scope error; the heartbeat handler was
not changed.

The same matrix also timed out during server teardown after a deliberately
failed outbox stop. Repeating embedded shutdown tried to republish Core
history after its journals had already closed, so the retained shutdown
coordinator retried indefinitely. The embedded owner now records when final
history was published and skips that phase on a certain, completed retry.
Its cleanup-failure test explicitly verifies the second close drains. The
installed `test_embedded_dispatch.py` file passed all 30 cases in 296 seconds,
including canceled observers, the cleanup failure, and retained-history
recovery, with no changed inputs.

Ubuntu shard 2 found an outdated protocol-limit test: its 2 MB frame no
longer exceeded the Core's 16 MB maximum. The stimulus now derives its size
from `MAX_FRAME_BYTES`; the installed oversized-frame case passed. The entire
installed startup-isolation file passed all 14 cases in 175 seconds on
Windows. Ubuntu shard 2 also failed the preauthorization restart case and
timed out after the prepare-stage cases; that Linux-only result is still
unclassified. Matrix `39239613854` was canceled after these findings.
The full Nexus matrix remains required.

Matrix `39269210262` on `77e74d7` has confirmed the two restart readiness
fixes: Ubuntu 3.12/3.13 and Windows 3.12/3.13 shard 0 passed. Windows shard 1
and 3 then exposed three distinct remaining test expectations. A
preauthorization-restart case and a released-resource restart case admitted a
new operation before the selected binding's inventory observation was fresh.
Both now wait for the same executor, observation, and binding admission facts
already required by the other restart tests. A no-effect dispatch refusal
sometimes retained the valid terminal `FAILED/NONE` state instead of the
also-valid `CLOSED/CLOSED`; its test now accepts both and verifies there are
no nonterminal operations or Core runtime owners. Finally, the 100-candidate
handoff scale case occasionally claimed one winner whose initial open failed.
Its fixture had established candidate observations but not fresh admission
for all 100 bindings. It now waits for those facts before competition and
reports the parent receipt/session evidence if a failure recurs. Nine
targeted installed cases covering those changes passed locally. The Ubuntu
shards of that matrix were still running at this checkpoint; no final
full-matrix result is claimed.
