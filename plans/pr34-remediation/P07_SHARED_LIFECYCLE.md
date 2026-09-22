# P07/P08 — shared connection and observable close

Parent: `0ad7c0f`; branch `feature/v0.2.0`. Partial phase checkpoint.

## Reproduction and correction

`test_closing_one_codex_session_preserves_other_thread_and_process` opens two
endpoints through the real REST app/supervisor and the real Codex transport,
using one scripted Python JSON-RPC peer. Before correction, closing the first
runtime killed the common process (`returncode=1`) and broke the second.
This was a behavioral RED, not an import/mock failure:
`evidence/p07-shared-connection-red.log`.

`RuntimeConnectionLifecycle` now owns resources for a connection. Both starting
and live sessions hold leases. Cancellation of one lease preserves siblings;
the final lease closes admission before teardown. Scope cancellation still
rejects late resources and bounded workers retain their slots. Explicit reuse of
a native connector maps to one connection key; connection contexts must match
agent, project, profile ID/revision and adapter kind. Normal connector factories
are unchanged: this does not add an undocumented global process pool.

Connection UUIDs now use migration 030's existing `harness_sessions.connection_id`
column and reach journal frames. No duplicate ownership table was introduced.
Codex's single stdout reader remains in place. Session-scoped event subscriptions
filter at fanout, preventing cross-session duplicate projection and allowing a
closed thread's pump to drain/exit while sibling threads continue.

Close denies further sends by removing the live entry, captures `stop_requested`,
requests native teardown, drains the pump within its bound and captures an
observed outcome. Repeated/concurrent closes reuse the in-progress or durable
state. A last lease may close the process; an intermediate Codex unsubscribe
records `detached`, with no fabricated native `ENDED`. Owned-process observation
uses the actual process object/handle, outside database transactions. An active
turn or failed drain/teardown is `outcome_unknown`, with binding quarantine.

Migration **034** adds explicit `HarnessEvent.origin` (`native` by default for
legacy rows). Supervisor-generated lifecycle events use `nexus`; an origin string
inside a peer payload is not trusted. The projector verifies connection identity
and commits lifecycle/presence/checkpoint atomically. A failed projection retains
the closing entry and durable journal record; retrying close does not repeat the
external stop. Recovery releases the entry only after projection commits.
Observed native event timestamps update only the matching runtime presence;
recovery time is not treated as proof that an old process is currently alive.

## Checks

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py -q --tb=short`
  — initial **1 failed**, expected wrong shared-process termination; RED log above.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py tests/test_runtime_process_ownership.py -q`
  — **9 passed**, `evidence/p07-shared-connection-progress.log`.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py tests/test_runtime_process_ownership.py tests/test_runtime_event_journal.py -q`
  — **19 passed**, `evidence/p07-lifecycle-progress.log`.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py -q`
  — **6 passed** after adding concurrent-close/drain and profile-context cases,
  `evidence/p07-shared-lifecycle-expanded.log` (earlier four-case log retained).
- Set `OKTO_NEXUS_PI_LIVE=0`, `OKTO_NEXUS_CODEX_LIVE=0`,
  `OKTO_NEXUS_CLAUDE_LIVE=0`, then:

```
.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py tests/test_runtime_process_ownership.py tests/test_runtime_event_journal.py tests/test_runtime_outbox.py tests/test_runtime_grants.py tests/test_runtime_endpoints.py tests/test_pr34_remediation.py tests/test_harness_codex_connector.py tests/test_harness_pi_connector.py tests/test_harness_claude_code_connector.py tests/test_import_boundary.py -q -k 'not expired_relay'
```

**189 passed, 9 skipped, 1 deselected, 1 warning**, 204.72s,
`evidence/p07-shared-lifecycle-gate.log`. The warning remains the intentionally
raised Pi reader callback exception. Native skipped cases are NOT_RUN. The
deselected causal-relay case remains P10 work.

After the presence projection adjustment:
`.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py tests/test_runtime_endpoints.py tests/test_runtime_event_journal.py -q`
— **34 passed**, `evidence/p07-shared-presence.log`. Ruff on changed Python: PASS.

## Limits / next dependencies

This provides fixture evidence for T-LIFE-07/08 and part of durable lifecycle
recovery. It is not a new native-model campaign; NATIVE_CAMPAIGN.md identifies the
earlier actual CLI executions. Native shared-session/active-turn close, steering,
interrupt, approvals, pressure and process-kill cuts remain to be verified.

Codex currently unsubscribes on `end`; an active turn therefore produces unknown
outcome rather than a claimed completion. Coordinated interrupt/settle before
unsubscribe is still needed. No session resume or native dedupe is invented.

POSIX owner-crash protection and replacement of the snapshot watchdog, startup
reconciliation/boot policy, protocol version/capability probes, native buffer
limits, connection-wide shutdown budget and operator recovery controls remain
pending. Operation/result/handoff/root correlation and authorized publication
remain P08–P10 dependencies. The final gate has not passed.
