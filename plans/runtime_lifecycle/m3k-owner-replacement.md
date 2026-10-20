# M3k: automatic replacement after host containment

Status: replacement and caller-notification correction passed source, installed
and disposable real Pi UI qualification. Idle/active preserve-agent resets also
passed through the UI. Global rollout remains pending. See `m3k-real-ui.md`,
`m3k-reset-ui.md` and `m3k-notifications-results.json`.

L10 is distinct from initial-start retry and per-agent recovery: once a shared
embedded dispatch owner failed, it stopped itself and contained native work,
but nothing created its successor while HTTP remained alive.

The new serve-owned supervisor monitors that failure and obeys the existing
automatic-recovery policy. It stops approved endpoint boot and inventory
production, requests retained dispatch cleanup and waits for DRAINED. Native
ownership uncertainty, unfinished openings, pending publication, journal readers,
discovery threads or probes prohibit replacement. Observation timeouts are not
release evidence. HTTP and the exclusive store owner remain alive throughout.

Only then does it join inventory publication/release and claim a successor.
The claim transaction checks the exact predecessor generation, same current
store owner, unrevoked executor and DISCONNECTED state. It increments the
executor generation even though the HTTP/store-owner process did not change.
A changed owner/generation is never taken back automatically.

The successor reuses the existing journal directory and normal independent
reconciliation, then resumes approved boot and new requests. It never replays
previous native commands. The old native factory override, capacity support and
host slot limit are preserved. All references used by HTTP, reset and shutdown
change together before successor dispatch starts.

Shutdown fences replacement synchronously, joins its retained task and then
drains the current bundle. If shutdown wins while the old owner is uncertain,
it must not start a successor when that uncertainty later resolves. Database
reset requires the previous supervisor to have drained before constructing a
new one. A partially claimed candidate is retained through errors and joined
on shutdown; no lock or history is cleared to force progress.

Required qualification includes all three adapter paths, one native effect
despite replacement, held native cleanup and discovery/probes, stale-owner
refusal, policy opt-out, shutdown/reset races, installed-package validation,
and a disposable real UI milestone. Production generation 73 remains unchanged.
This checkpoint does not complete M3, M6 (separate-process supervisor experiment)
or the full UI-A gate.

## Source qualification

The first six focused cases passed in 92.87 seconds, including all three
adapters, uncertain native cleanup with/without server shutdown, and rejection
of a changed generation. An expanded source campaign then passed 28 cases in
358.13 seconds, adding held inventory production, policy opt-out/re-enable,
successor claim contention, diagnostic contention, storage cleanup ordering
and independent reset readiness.

Review identified a transient candidate-release failure during supervisor
shutdown. A new regression failed before the fix (`m3k-cleanup-before.xml`):
the release error escaped the supervisor and prevented a successful join.
Shutdown now retains and retries that same candidate until cleanup succeeds;
it never clears the resource reference on an error. Final source and installed
qualification also cover an opening that returns its native handle after
containment started, and a new turn on the successor without replaying the old
turn. The final focused source campaign passed all 12 cases in 147.75 seconds.
The wheel and sdist were built from the final source with a fresh dashboard
compilation. A new isolated Python environment installed the wheel alongside
the qualified Core/Connector wheels; all 49 installed dependencies are compatible.
The installed campaign passed **82 cases with no failures or skips** in 1169.59
seconds, covering replacement, shutdown, reset, diagnostic contention, normal
dispatch and automatic recovery. Inputs remained unchanged; 536 non-generated
source files match the wheel. The installed application and both dependencies
were byte-verified against their artifacts. See `m3k-results.json`.

These tests use synthetic native peers, real durable SQLite and real HTTP/CLI
shutdown paths. They do not establish a real provider fault-injection UI result.
The later disposable real-provider test is recorded in `m3k-real-ui.md`, including
its caller-notification failure. The automated result above is not superseded
by or sufficient to close that live acceptance finding.

Nexus wheel SHA-256: `bdeb038d0c1a4d8e7ed167b9fc07faf91875871113cd3c53fdaba119d0cab876`.
Source reports: `build/m3k-owner-source.xml`,
`build/m3k-owner-source-expanded.xml`, `build/m3k-owner-source-final.xml`.
Installed reports: `build/runtime-m3k-owner-installed/`.
