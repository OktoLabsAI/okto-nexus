# M4d3 — Retire sessions that never admitted native execution

Status: installed qualification passed; checkpoint ready for publication on the
feature branch. Global rollout remains pending.

The previous maintenance query required a local stream. A terminal opening
refused before native admission never has that stream, so every later restart
repeated its history verification. The new query discovers terminal sessions
through their canonical opening. It preserves the existing streamed release
path and gives no-stream refusals a distinct `no_native_admission` checkpoint.

Retirement requires either an authenticated initial lease refusal with the exact
Core receipt, or a proven dispatch/preparation refusal. All session operations
must be terminal, the lease closed/absent, local events absent and native
producers/resources absent or released. Tools must finish cleanup. The final
transaction rechecks evidence and its revision. Migration 147 invalidates the
checkpoint when supporting operation, receipt, dispatch, denial, publication or
capacity evidence changes. No fake native stream, process exit, reply or ACK is
created. Pending first dispatch remains eligible for execution.

Released provisional slots retain an opaque Core identity. Core now resolves
that identity from an exact released observation, without granting release or
replay authority. Nexus inspects historical capacity through the ledger, rather
than reauthorizing an old request under the new productive generation.

## Qualification record

- The pre-fix restart reproduction failed its new retirement assertion.
- Early implementation runs exposed the productive-generation lookup and the
  released provisional-slot association gaps; both were corrected.
- The final refusal/restart source campaign passed 20 cases, including six
  durable crash boundaries and second boots that do not reopen retired history.
- Four additional resource checks cover an occupied slot, orphan sidecar,
  missing ledger and unexpected Core receipt. Their first exploratory run had
  an incorrect test import; it was fixed before the current campaign.
- Core installed: 38 passed, exact artifact bytes verified.
- Connector installed: 68/70 initially passed; both timeout cases passed
  unchanged in a focused retry with the same artifacts. No timing fix claimed.
- Nexus source retirement/cost campaign: **55 passed**, including history sizes
  of 1k/10k/100k and unchanged SQL work limits. The installed campaign passed
  **61 cases** in 1118.30 seconds, with `status=PASS`, `changed_inputs=[]`, exact
  installed package verification and no skipped cases.

In all three history sizes the retirement selection used 214 SQLite VM steps,
pending-subject lookup 263 and retirement commit 414. The measured query work
did not grow with terminal history. All 547 Nexus package files match the
current source byte-for-byte; the installed runner separately verifies package
bytes. The isolated dependency check reports no broken requirements.

Core commits: `feae7fe`, documentation alignment `57fa45a`.
Connector commit: `1b12367`.

Artifact hashes:

| Package | SHA256 |
| --- | --- |
| Core 0.0.12 | `fffcfad6a82a67fb4b9cc4b25b0718a3c3e30bf119dde71ee07dcb062b814898` |
| Nexus 0.3.1 | `bb9a0e2cf97af2ba04b20a59ab9df0feb885e1ffbe4d46bf4a3b869fcbc5bffe` |
| Connector 0.0.10 (unchanged) | `41331e7b9405e830d990141e48e7702d461559a779b66ee39ec8aedc9e52d7c2` |

Build/test directories labeled `m4d2` predate the canonical checkpoint-number
correction and retain their original names. Nexus installed campaign:
`build/runtime-m4d3-unopened-installed/`. Installation is isolated under
`build/m3k-owner-env`; production generation 73 was not replaced.

This closes only the no-stream retirement gap after qualification. Initial
audit frontier, scan caps, stream fairness, real-history latency and the other
M4 acceptance items remain pending. Existing major UI gate evidence remains
recorded under M3k; no new real-provider or physical remote-host gate is claimed.
