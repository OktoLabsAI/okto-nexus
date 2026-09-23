# P10 — whole-process relay recovery

Parent SHA: `6b03ba960ce5a1670f35e41d27ab2d7b6848ffea`, branch
`feature/v0.2.0`, 2026-09-23. No production changes or migration in this unit.
PR34 rechecked: OPEN, head `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`,
base `27b06fe48b9f95b35c94f50827fea83d178f4e12`.

## Executed scope

`tests/runtime_relay_process_fixture.py::main` launches the production bootstrap,
HTTP app, owner, dispatcher and actual Codex connector against a disposable
JSON-RPC Python peer. Each server has its own OS process and temporary store;
authenticated HTTP/MCP requests create profiles, endpoints, sessions and messages.
Fixture credentials are generated locally and retained across restarts. No
personal credentials, operator key, model or provider is inherited.

`test_whole_owner_crash_preserves_relay_lineage_and_never_replays_ambiguous_child`
terminates the entire server at three cuts:

- Terminal journal append/fsync returned, projection has not committed.
- Result publication and child admission committed, child not dispatched.
- Child peer emitted acceptance, with no terminal result available.

The next server opens the same store and uses ordinary startup recovery. Tests
check exact root, deadline, budgets, operation IDs, envelope depth, publication,
foreign keys and peer writes. The ambiguous child becomes `OUTCOME_UNKNOWN` and
is never resent. A fourth case recovers the durable result after its root deadline:
publication survives, but no child execution is admitted. Windows process handles
and Linux pidfds acquired before the crash prove the owned peer exits, without
PID scanning or signalling potentially recycled numeric PIDs.

`test_slow_canonical_chain_keeps_deadline_across_four_server_processes` starts four
actual servers at application clock offsets 0/10/20/30 minutes. Continuations keep
the original deadline and depth limit four; the final continuation is rejected.
A separate authenticated entry starts a new root. This case tests logical inbox
admission with no endpoint; the crash cases separately exercise native transport.
Time is simulated at the application clock, not by rewriting persisted leases.

## Commands and observations

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay_process_restart.py -x`
  initially **FAIL**: 1 failed in 6.47s. Fixture incorrectly unpacked
  `ensure_operator_key` on restart (it returns None for an existing operator).
  Corrected fixture credential reuse; this was not a production behavioral RED.
- Same command after correction: **PASS**, 3 passed in 24.83s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay_process_restart.py`:
  **PASS**, expanded 5 passed in 47.50s, Windows.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_relay_process_restart.py`:
  initial **FAIL**, 4 failed / 1 passed in 54.13s. Standalone CPython lacks
  `os.pidfd_open`; test now uses the existing guarded Linux pidfd wrapper.
  Repeated command **PASS**, 5 passed in 73.22s. No production modification.
- `rtk proxy .venv/Scripts/python.exe -m ruff check tests/runtime_relay_process_fixture.py tests/test_runtime_relay_process_restart.py`:
  **NOT_RUN**, Ruff is not installed in that venv.
- `rtk proxy ruff check tests/runtime_relay_process_fixture.py tests/test_runtime_relay_process_restart.py`:
  **PASS**, all checks passed using installed Ruff.

## Limits and next dependency

Additional correlation coverage on the same parent:

- `tests/test_runtime_relay.py::test_same_agent_on_distinct_endpoints_keeps_operation_parent`
  sends separate roots to two approved live endpoints of the same worker. Exact
  source-result joins verify the child root, native session and counters.
- `tests/test_runtime_causality.py::test_authenticated_reply_inherits_root_instead_of_starting_a_new_budget`
  now includes forged root/depth/parent/budget values in the message body with
  tracing disabled. Persisted envelopes retain server-derived values.
- `tests/test_runtime_relay.py::test_explicit_three_agent_chain_preserves_initiator_and_budget`
  uses an approved direct notification target for caller → worker → observer;
  the original actor and root remain bound, and the next hop exceeds the budget.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py tests/test_runtime_causality.py tests/test_runtime_notify_targets.py`:
  **PASS**, 55 passed in 211.60s. Run precedes the additional three-agent case.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py -k explicit_three_agent_chain`:
  **PASS**, 1 passed / 22 deselected in 9.86s.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_relay.py tests/test_runtime_causality.py tests/test_runtime_notify_targets.py`:
  **PASS**, 55 passed in 217.13s; likewise precedes the three-agent addition.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_relay.py -k explicit_three_agent_chain`:
  **PASS**, 1 passed / 22 deselected in 13.17s.
- `rtk proxy ruff check tests/runtime_relay_process_fixture.py tests/test_runtime_relay_process_restart.py tests/test_runtime_relay.py tests/test_runtime_causality.py`:
  **PASS**. `rtk git diff --check`: **PASS**.

These are real server/process crashes with protocol fixtures, not real-model
campaigns or physical power-loss tests. Native Codex/Claude relay remains NOT_RUN;
Pi and dedicated Claude attach native remain NOT_RUN as previously scoped.
T-RELAY-02/03 and T-JRN-02 now have executed process evidence. Other crash cuts,
the aggregate P10 gate, P11/P12 and final build/install remain pending. No phase
or final gate is promoted by this unit.
