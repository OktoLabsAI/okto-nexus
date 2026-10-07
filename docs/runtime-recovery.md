# Runtime recovery and availability

The embedded executor owns shared storage, but recovery readiness belongs to each
agent. A failed or slow subject must not stop an unrelated subject, prevent new
agent configuration, or change the remote Connector connection contract.

## Recovery boundaries

- The host checks its exclusive store ownership, ledger scope and untracked Core
  resources. Loss of these shared guarantees still blocks the host.
- Each local agent has durable readiness tied to the executor generation.
  Admission, dispatch selection, lease issuance and capability use check it.
- Each agent has at most one recovery/publication worker. Slow workers remain
  owned and observed; a five-second observation deadline fences that agent
  without cancelling a journal writer or spawning duplicate attempts.
- Failed attempts retry with increasing delay and jitter, up to approximately
  thirty seconds between attempts. There is no final retry count that abandons
  an otherwise recoverable agent or an unclaimed message.
- Recovery contains only that agent's sessions, joins its admitted producers,
  drains captured receipts/events and verifies resource release. It never
  replays a turn whose native effect may have occurred.
- Previously inactive or archived identities remain inactive or archived.
  Historical native approval requests cannot become actionable during recovery.
- Closed streams stop being polled only after release evidence and matching
  committed event watermarks. This avoids accumulating recurring work for old
  sessions without discarding their durable history.

The Agents view reflects each local agent's state. Last-resort recovery accepts an
optional `agent_id` on `/v1/runtime/recovery/retry` and
`/v1/runtime/recovery/plan`; the confirmation is bound to the exact returned plan.
It cannot release another agent's active sessions.

## Restart behavior

The serve lock and runtime owner lease record the local process owner. A
read-only OS observation of a confirmed exited same-host process permits immediate
takeover. A live process, permission error or uncertain observation does not.
Windows uses a synchronization handle, never `os.kill(pid, 0)`.

Native processes are recovered using the Core's recorded owned-container evidence,
not by killing historical PIDs. A crash before binding/opening can be settled only
after proving the absence of publication, Core history and owned resources. That
proof remains recognizable on subsequent restarts.

## Validation

`tests/execution_r4/test_agent_recovery_isolation.py` covers:

| Scenario | Required result |
| --- | --- |
| One local journal unavailable | Healthy agents execute; only its subject recovers |
| One journal read suspended | One retained worker; other agents remain available |
| New local agent during recovery | Configuration, admission and execution succeed |
| New remote agent during recovery | Registration and three WSS reconnect/heartbeat cycles succeed |
| Archival during failed recovery | History drains without reactivating the identity |
| Live event projection failure | Only its agent is contained; automatic recovery restores new admission |
| Final event captured while closing | Event commits before the closed stream stops being polled |
| Orderly owner process termination | All retained sessions reconcile on restart |
| Forced owner process termination | Real Windows Job peers stop; locks and resources recover automatically |
| Forced termination before binding | Unstarted work is settled without a native replay |
| Three successive restorations | No old operation is resent; new local/remote agents can be added each cycle |

The destructive scenarios use disposable homes and real Windows processes with
synthetic native peers. They validate Nexus/Core ownership and recovery rather
than provider model behavior. Remote transport tests additionally exercise the
real Connector's cold event recovery, lease renewal and active disconnects.

Other regression coverage includes owner fencing, event ACK idempotency, native
decisions, capability/session reuse, capacity, shutdown storage ordering and real
serve signals. Older legacy-integration fixtures target setup APIs that have
already been removed; they are not substitutes for the canonical R4 scenarios.

Validation on Windows, 2026-10-06: all seven isolation scenarios passed, including
real process termination and repeated restoration. The final combined run with
pre-open recovery and runtime qualification passed nine cases; the final-event
scenario passed separately. Four real Connector transport scenarios also passed.
The frontend production build passed. These are targeted regression suites, not
a claim that every legacy repository test passes.

After installing the global build and gracefully restarting the existing Nexus,
the embedded executor reached `CONTROL_READY`, all eleven local historical
streams were drained, and Pi, Claude and Codex reported `Ready`. The archived
agent remained inactive. The existing disconnected remote host remained
`Offline`, independently of local recovery.

## Integration choices

Keep a shared host for discovery and ownership, and independent agent workers for
recovery and publication. Separate OS processes per agent are not required to
isolate a history error, and would introduce additional lifecycle coordination.
Keep native sessions lazy: a recovered agent can accept new work without eagerly
reopening every historical process. Preserve durable, idempotent event ACKs and
operation fences instead of retrying ambiguous native commands.

Availability still depends on the Nexus process, shared database and machine
being operational. Permanent corruption, exhausted machine resources or revoked
external credentials cannot be corrected by replaying requests. Those conditions
must remain visible and scoped as narrowly as the available evidence permits.
