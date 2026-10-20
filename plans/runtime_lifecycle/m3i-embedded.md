# M3i embedded producer integration

Status: installed qualification passed. Global rollout and real UI gate pending.

The embedded host now runs one retained Core observation worker per discoverable
harness. Publication has its own loop and retains the exact accepted candidate
batch and coverage. A slow or failed adapter does not prevent sibling inventory
publication. Full refresh completion waits for a post-request frontier and fresh
completed coverage; partial and failed publications cannot falsely acknowledge it.

Version checks hold only their selected adapter. Configuration and probes resolve
against the coverage of the accepted batch. Sibling publication during a probe
is permitted only if the selected evidence remains exactly identical; ownership,
permissions, source bytes and consent are still checked. A successful stored
observation can be published after a temporary publication failure without
repeating the native probe.

Shutdown fences observation and retains all worker/probe/publication joins before
releasing ownership. Cancellation of a caller does not release native producers.

Automatic boot now revisits deferred endpoints when another inventory publication
arrives. Already admitted endpoints are excluded from later passes. Immutable
blocked or expired resolutions need a new attempt identifier: the writer-serialized
lookup requires no admitted operation and a resolution that cannot be submitted.
An admitted operation always retains its original intent, including after a lost
reply or later inventory loss.

## Evidence in progress

- Seven initial independent producer/boot-owner tests passed. They cover HTTP
  during held Pi discovery, sibling publication, actual canonical Codex open/turn
  through a synthetic native peer, failed-adapter retry, and retained boot waits.
- Eight focused retry tests passed, including canonical boot recovery, admitted
  intent preservation, failed refresh retry and committed-observation publication.
- The HTTP version-check scenario passed while Pi discovery remained held and
  Claude discovery changed to FAILED during the Codex probe.
- The broader source draft reached canonical boot with the earlier loaded code
  and retained an immutable `inventory_not_fresh` resolution, no admitted
  operations, and a CONTROL_READY host. Its exact test process was stopped
  after preserving stacks and read-only database evidence. This is a reproduced
  boot defect, not a passing campaign or an observation timeout. The subsequent
  focused canonical retry tests passed with the new no-admission lookup.
  An earlier draft found seven
  failures: full-scan assumptions in publication counts and error/wait semantics,
  plus freshness invalidation and publication retry issues. Both product defects
  were corrected; final installed qualification is required before rollout.
- Source fixture discovery doubles now honor the requested adapter scope.

This does not complete M3 or the real UI gate. Connector's independent producer
was subsequently qualified, as recorded below.
The live global generation 72 remains unchanged on the previously qualified build.

## First installed campaign — not yet qualified

The fresh installed environment completed 121 cases: **111 passed, 8 skipped,
2 failed** in 2081.75 seconds, with `changed_inputs=[]`. The skipped cases are
the optional automated browser workflow suite; they do not establish the real
UI gate. All independent producer/probe/boot cases passed, including the
previously blocked canonical boot scenario.

Both failures are the reset-preserving-connection cases (idle and previously
active). Reset has returned completion before the replacement owner's selected
observation is accepted; the immediate message is refused with
`inventory_not_fresh`. The same reset flows sometimes pass when publication
wins the race. Configuration preservation checks passed before the send.
This readiness/admission interval is recorded as L17. Do not hide it by
repeated sends, weakening freshness checks or simply waiting in the test.
No global rollout or completed embedded checkpoint is claimed.

The reset fix keeps its owned operation in `reconnecting` until fresh accepted
observations exist for preserved enabled local connections. Dispatch admission
has already reopened, so ready agents remain independent; unconfigured harnesses
and remote hosts do not delay this local reconnection phase. This waits on the
existing producers and does not trigger another scan. Shutdown interrupts the
wait with explicit information that history was already reset.

All eight existing reset cases passed in the subsequent source campaign. Two
new isolation cases initially asserted HTTP 202 on a status GET, which always
uses HTTP 200 and represents ongoing work with `pending=true`; that test
observation was corrected. Both new cases then passed in 74.57 seconds: a held
selected harness keeps reset pending, while a held unused Pi allows reset to
finish and the selected Codex session to receive its message. The rebuilt
installed qualification remains pending. Neither existing failing reset test
was relaxed.

Reports: `build/runtime-m3i-embedded-installed/` and
`m3i-embedded-first-results.json`. The Connector's actual independent producer
is now implemented separately and undergoing installed qualification.

The Connector's producer checkpoint is now qualified: 164 installed cases,
commit `b12b8b8` pushed to `feature/v0.0.10`. Its wheel is synchronized into the
Nexus CI vendor for the joint build. This has not updated the global instance.


## Final installed checkpoint — joint artifacts

The rebuilt Nexus wheel with qualified Core/Connector dependencies completed
**115 passing tests, eight skipped, zero failures/errors** (1023.30s).
Inputs remained unchanged. Every overlapping non-generated source/package file
matched the wheel (535 files); dashboard assets were rebuilt by tsc/Vite
from the frozen frontend inputs. Installed packages were byte-verified and all 48
dependencies checked. Exact wheel hashes: `m3i-embedded-results.json`.

Both original immediate-send reset regressions pass without changing their
assertions. The deterministic cases prove reset waits for a preserved selected
harness, but does not wait for an unused held Pi before completing and delivering
to Codex. The remaining cases cover boot, version checks, revalidation, partial
publication, retry and retained shutdown. The eight skips are optional automated
browser tests, not successful UI checks. Global rollout and real UI remain pending.

At 07:30–07:32 UTC, the reported all-Recovering state was inspected again without
restart or browser reload. The live global generation 72 retained CONTROL_READY,
all three local agents READY, renewed leases and four Pi WARM slots. Both existing
tabs showed Online. Their last-contact observation was older than the current
heartbeat; background polling pauses while hidden. This is only a possible
explanation for display lag, not proof of the incident's cause. One Pi publication
delay at 07:03 did not change its durable READY state. L12 remains open.
