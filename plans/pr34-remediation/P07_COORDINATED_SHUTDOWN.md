# P06/P07 — Coordinated drain and wake generations

2026-09-23. Parent e482655, branch feature/v0.2.0. No migration.
P06/P07 remain IN_PROGRESS; this is not the final gate.

Behavioral RED: the actual HTTP app lifespan released its dispatcher owner while
one runtime remained live. The regression failed on the observed release order,
not an absent import. See evidence/p07-shutdown-red.log (concise transcription).

Production lifespan now quiesces dispatch and supervisor admission, uses at most
four teardown workers, and retains the owner heartbeat and journal until startup,
send calls, bounded native helpers, event pumps, closing sessions and dispatch
workers drain. Journal projection drains before journal close and owner release.
The application wait has a global ten-second budget. On expiry it reports pending;
the existing coordinator keeps ownership and finishes after activity ends. It
does not launch replacement workers or declare an unobserved process exit.
Process exit still relies on the established Windows Job/Linux guardian ownership.

An open that finishes concurrently with shutdown closes its newly created session
and returns an error. Subsequent open/send calls are rejected. A contending serve
now refuses startup instead of exposing an app without runtime ownership. Wake
generation plus a Condition replaces Event.wait/clear, preserving wakes received
before a wait and during a bounded scan. Dispatch failure persistence also checks
the current owner before updating the old attempt.

Changed symbols: RuntimeDispatcher.wake/_wait_for_wake/quiesce/finish_shutdown_when;
HarnessSupervisor.begin_shutdown/drained and activity tracking; shutdown_runtime;
HTTP app lifespan. Public envelope, journal and connector contracts unchanged.
Direct control durability and expected-turn semantics remain separate pending work.

Evidence (commands executed with rtk proxy):

- `.venv/Scripts/python.exe -m pytest -q tests/test_runtime_shutdown.py tests/test_runtime_wake_generation.py tests/test_runtime_outbox.py tests/test_runtime_shared_connection.py tests/test_runtime_process_ownership.py tests/test_runtime_result_correlation.py tests/test_runtime_event_journal.py tests/test_import_boundary.py`
  — 55 PASS, 60.96s; evidence/p07-shutdown-gate.log.
- A preceding run had 54 PASS / 1 FAIL because the new startup refusal was wrapped
  by the MCP task group. Ownership acquisition now precedes that task group;
  the gate above validates the final composition and direct failure.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short`
  — REAL isolated local Codex, 2 PASS / 1 deselected, 15.46s;
  evidence/p07-shutdown-native-codex.log.
- Same native command with `-k claude_code` — REAL isolated local Claude stream,
  1 PASS / 2 deselected, 8.21s; evidence/p07-shutdown-native-claude.log.
  Explicit executable/login-source paths and isolated profile setup are unchanged
  from NATIVE_CAMPAIGN.md. Login copies are removed by fixture finally blocks.
- Ruff on changed Python files and `git diff --check`: PASS.

Native cases cover two-turn delivery/result/consumption and Codex explicit active
close, not a newly executed native multi-runtime shutdown stress test. Global
shutdown concurrency, delayed helper, startup race and ownership retention are
covered through production HTTP composition with fixture peers. Pi/attach native
remain NOT_RUN. Full Linux composition, full compatibility suite and final local
reinstall remain NOT_RUN. No broad phase was promoted to VERIFIED.

PR34 rechecked with `gh pr view 34 --repo OktoLabsAI/okto-nexus --json headRefOid,baseRefOid,headRefName,state`:
OPEN, feature/harness-integrations, HEAD d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397,
base 27b06fe48b9f95b35c94f50827fea83d178f4e12; no later PR changes to reconcile.

Next dependency: reconcile previous owner sessions and journaled old-attempt
results on restart before implementing stable endpoint boot. A historical
protocol_ready row is not proof of a currently usable connection. Authorized
publication/artifacts, durable controls, P09–P12 remain outstanding.
