# P07 — close an observed active Codex turn

Parent `866753a`, branch `feature/v0.2.0`. This unit does not complete P07/P08.

`CodexAppServerConnector._end` now fences new commands against a closing thread,
interrupts its observed active turn, and waits up to 2.5 seconds for that turn's
terminal notification before unsubscribing. It does not interpret the interrupt
response as completion. A missing or mismatched terminal records
`transport/close_unsettled` and retains uncertainty in lifecycle observation;
the supervisor quarantines that endpoint. The shared native process survives
when another session holds a lease.

`_on_notification` clears the active turn only for a matching terminal ID. It
queues that event and changes the turn state atomically under the session lock
before waking the close waiter. The recorded terminal precedes the final Nexus
lifecycle event. Detach still does not mean observed native session/process end.

Behavioral RED through the real HTTP composition:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py -q -k active_close --tb=short`

1 FAIL, 6 deselected: close only unsubscribed, leaving the held turn active and
`outcome_unknown`; `evidence/p07-active-close-red.log`.

After correction, the matching-terminal case passes and an added stale-terminal
case proves it cannot clear the active turn or remove endpoint quarantine. Both
use a scripted native peer with two threads in the production supervisor.

`.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py tests/test_harness_codex_connector.py tests/test_runtime_native_campaign.py -q --tb=short`

38 PASS, 4 skipped in 34.42s; `evidence/p07-active-close-gate.log`. Native tests are
opt-in and skipped in this fixture gate. Earlier progress: 37 PASS, 1 skipped
before adding the stale-terminal parameter (`evidence/p07-active-close-progress.log`).

Real native campaign, using the same explicitly approved Codex executable and
login-source paths documented in NATIVE_CAMPAIGN.md, with a fresh isolated
project/store/profile and only a temporary login copy:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_native_campaign.py -q -k active_close --tb=short`

**1 PASS, 2 deselected in 5.39s**, `evidence/p07-native-codex-active-close.log`.
Codex 0.155.1, observed gpt-6-astra / openai. A canonical inbox delivery started
the turn; close observed the matching `turn/completed` status `interrupted` at
sequence 10, before final lifecycle `stopped`. Owned process reaped; temporary
auth copy independently checked absent. Sanitized read-only observations from
the disposable test database are in
`evidence/p07-native-codex-active-close-observations.json`; no prompt output or
credentials copied to evidence. This run preceded the final lock-atomicity
refinement, whose fixture regression result is recorded separately below.

Final lock-atomicity regression:
`.venv/Scripts/python.exe -m pytest tests/test_runtime_shared_connection.py tests/test_harness_codex_connector.py -q --tb=short`
— 38 PASS, 1 skipped in 31.97s; `evidence/p07-active-close-atomic-gate.log`.
Ruff passed for the three changed Python files. No migration/schema change.

Remaining: a turn/start request awaiting native turn identity, concurrent sends,
pre-write registration of native response correlation and general durable
control-operation correlation are not resolved by this observed-active-turn
unit. Global shutdown budget, bounded native buffers and POSIX ownership remain
pending. Native multiplexing is still NOT_RUN (fixture multiplexing was run).
Pi and Claude attach native remain NOT_RUN; no extra Claude control claims.
