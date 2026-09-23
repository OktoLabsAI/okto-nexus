# Durable administrative commands — contract v2

Execution parent: `90ec3cc`, branch `feature/v0.2.0`, 2026-09-23. This unit does not close P07/P08 or the final gate.

Migration 040 adds `runtime_commands` and a separate command correlation FK on
`runtime_results`. Existing inbox/outbox identity and handoff ownership remain
unchanged. `RuntimeControlService` admits send/steer/interrupt/close in the same
transaction as grant consumption. `RuntimeCommandDispatcher` uses the existing
serve owner, recovery fence and wake generation. Five bounded workers reserve
separate capacity for turns, controls and close. A timed-out native call retains
its slot until it returns; uncertain effects never trigger automatic replay.

REST and MCP now return durable operation admission, not synchronous native
completion (`runtime_contract_version=2`). Clients supply `idempotency_key` to
survive a lost response. A server-generated key cannot protect a client retry
that lost that key. Read commands with REST
`GET /api/v1/harness/operations/{operation_id}` or existing MCP `harness_get`
with `operation_id`. A close response is an operation; inspect its result for
observed `stopped`, `detached` or `outcome_unknown`. HTTP 200 remains compatible
at the envelope level, but clients must migrate assumptions about completion.
Read authorization is checked against the bound session; payload identity is
never authentication. No extra MCP tool was added.

Controls carry expected operation/turn/owner fences. Codex and Pi in-place
steering keep original result correlation; Claude replacement steering binds
the next native turn to its own command. The journal projects either outbox or
command results using the same attempt, connection and recovery fences. A
terminal command event never automatically completes a handoff.

Validation performed on the working tree above this parent:

- Behavioral RED: admission blocked on native write and a duplicate command key
  caused two effects (2 failures before implementation).
- Windows command/grant/outbox/correlation/restart/shutdown integration:
  49 passed; expanded boot/session recovery suite: 67 passed before adding the
  final command crash-recovery test.
- Legacy REST/MCP and shared-connection compatibility: 45 passed, 2 POSIX skips.
- Linux command/grant/shutdown integration: 28 passed in 82.91s using
  `/var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q
  tests/test_runtime_commands.py tests/test_runtime_grants.py
  tests/test_runtime_shutdown.py --tb=short --maxfail=3` through WSL Ubuntu.
- New crash test initially raced journal append against failed projection;
  waiting for the injected projection failure fixed the cut. Focused test:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_commands.py::test_command_result_recovers_after_owner_restart_without_reexecution
  --tb=short`: 1 passed in 5.68s. Recovery retained output without another launch.
- Ruff selected changed production modules: PASS.
- Authorized real Codex 0.156.1: 2 passed, 1 deselected in 17.00s; Claude Code
  2.1.280: 1 passed, 2 deselected in 13.93s. See
  `evidence/p07-durable-commands-native-codex.log` and
  `evidence/p07-durable-commands-native-claude_code.log`. These cover two inbox
  turns and durable close, plus active close for Codex. Native steering/HITL
  were NOT_RUN. Pi and dedicated Claude attach remain NOT_RUN.

Remaining dependencies: result publication/artifacts/retention (P08), canonical
work/bootstrap/approvals (P09), persisted causal budgets (P10), administrative
surface/UI completion (P11), full matrix/build/install/operational gates (P12).
The known expired-relay regression is still pending P10; this unit does not
claim a green full repository suite.

Final expanded Windows command: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_commands.py tests/test_runtime_grants.py tests/test_runtime_outbox.py tests/test_runtime_result_correlation.py tests/test_runtime_restart.py tests/test_runtime_shutdown.py tests/test_runtime_boot.py tests/test_runtime_session_recovery.py --tb=short --maxfail=4`: **68 passed in 169.33s**. A subsequent response-key assertion passed separately (1 passed in 3.70s); admission now echoes the idempotency key.
