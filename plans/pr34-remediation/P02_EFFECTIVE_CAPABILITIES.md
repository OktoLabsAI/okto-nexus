# P02 — qualified session capabilities

Source parent: `575c8c28ab6c4543ad8dc5b0b64949d5f735fea6`; changes in this milestone.
2026-09-24, Windows and isolated WSL Linux. Schema057 unchanged; surface52,
identity reference19. Final remediation gate remains NOT PASSED.

## Behavior and implementation

An actual JSON-RPC peer with absent/unknown Codex version could admit a turn by
inheriting descriptor capabilities. Initial regression: **2 FAIL, 7.43s**.
An explicit factory sharing that unqualified connection across two approved
endpoints also opened a second native thread: **1 FAIL, 5.18s**. The preliminary
same-endpoint test passed because the existing single-executor rule blocked it;
that preliminary pass is not the sharing regression evidence.

`QualifiedConnector` is composed for every registered adapter, including extensions,
in production `construct_profile_connector`. After native startup, the trusted
descriptor probe intersects observations with descriptor and approved profile
restrictions. Missing probes fail closed. No network, process or secret resolution
runs inside a SQLite write transaction. The stored compatibility_report is
server-owned; caller metadata cannot change it. Existing port protocol attributes
are explicit on the wrapper; cleanup delegates to the original connector.

`runtime_requirements` validates restrictions and effective capabilities.
`runtime_control`, `runtime_delivery`, `runtime_work`, `runtime_native_approvals`
enforce them with existing authorization/revision checks. The native send boundary
rejects unsupported writes using RuntimeCommandNotSent. `runtime_dispatcher`
records REJECTED/native_write_not_started with ACK NONE, not OUTCOME_UNKNOWN.
Its logical inbox reservation remains intact; there is no automatic second executor.
`harness_supervisor` checks effective multiplexing for automatic and explicit reuse.

`runtime_discovery` exposes current-owner ready-session capabilities independently
of endpoint declarations and historical reports. Runtimes renders this distinction.
Managed work requires events and correlated results; approvals require HITL.
Profile restrictions cannot disable the safety constraint interrupt_requires_settle.
No inferred native ACK, deduplication, replay, general sandbox guarantee or authority.

## Tests and observed results

All commands below use `rtk proxy`; Python is `.venv/Scripts/python.exe` on Windows.
Linux prefix: `wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus --
/var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python`.

- `python -m pytest -q --tb=short tests/test_runtime_effective_capabilities.py`:
  initial 2 FAIL7.43s. Intermediate 2 FAIL4.19s exposed static Protocol attribute
  checks; 2 FAIL6.41s then exposed an incorrect test expectation (CONFIG_ERROR is
  HTTP500, not422). Corrected 2 PASS6.04s. Later expanded 9 PASS43.72s.
- `python -m pytest -q --tb=short tests/test_runtime_effective_capabilities.py tests/test_pr34_remediation.py tests/test_runtime_commands.py tests/test_runtime_capability_admission.py`:
  Windows54 PASS106.29s (early intersection implementation).
- `python -m pytest -q --tb=short tests/test_runtime_effective_capabilities.py tests/test_runtime_compatibility_observations.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_approvals.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_relay.py tests/test_runtime_production_multiplex.py`:
  Windows78 PASS4 FAIL275.82s; four obsolete exact-report expectations corrected.
- `python -m pytest -q --tb=short tests/test_runtime_effective_controls.py tests/test_runtime_compatibility_observations.py tests/test_runtime_effective_capabilities.py tests/test_runtime_effective_requirements.py tests/test_runtime_discovery.py`:
  Windows32 PASS81.44s after correcting two old unknown-version tests that expected
  conversation to remain executable. Prior result30 PASS2 FAIL83.70s retained.
- `python -m pytest -q --tb=short tests/test_runtime_effective_capabilities.py tests/test_runtime_effective_controls.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_approvals.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_production_multiplex.py`:
  Linux67 PASS236.49s before final explicit sharing guard.
- `python -m pytest -q --tb=short tests/test_runtime_effective_capabilities.py tests/test_runtime_production_multiplex.py tests/test_runtime_shared_connection.py`:
  final sharing guard Windows26 PASS98.74s; Linux26 PASS103.98s.
- `python -m pytest -q --tb=short tests/test_runtime_effective_capabilities.py tests/test_frente1_resources.py`:
  Windows27 PASS40.47s; Linux27 PASS50.83s, including no-probe fifth extension and invalid profile restrictions.
- Isolated UI campaign (`OKTO_NEXUS_UI_CAMPAIGN=1`),
  `python -m pytest -q --tb=short tests/test_runtime_diagnostics_dashboard.py`:
  9 PASS70.19s before final explanatory wording. Temporary Vite build and sandboxed
  Edge, network blocked except loopback fixture; generated repository assets untouched.
- `node node_modules/typescript/bin/tsc --noEmit` from frontend: PASS.
- `python plans/pr34-remediation/measure_surface.py 575c8c2`: PASS; OFF43 tools,
  40448 chars/10112 estimated tokens; ON51 tools,47730 chars/11932 estimated tokens.
  No resident schema growth. Revision51→52; reference docs load on demand.
- Ruff on every changed Python file: PASS.

Selections overlap; counts are not additive and do not imply a full-suite PASS.

## Real isolated campaigns

`tests/test_runtime_native_campaign.py` under disposable `--basetemp`, with explicit
`OKTO_NEXUS_NATIVE_CAMPAIGN`, `OKTO_NEXUS_TEST_EXECUTABLE` and
`OKTO_NEXUS_TEST_AUTH_SOURCE`; legacy CODEX_LIVE/CLAUDE_LIVE flags both0.
No operator key supplied to native children. Login files copied only to disposable
native configuration and removed by teardown; no personal hooks/settings/sessions.
Native ownership teardown completed. Server-owned observations preserved in
`evidence/p02-effective-native.json`; collection script reads only those reports.

- Codex0.156.1, selector `codex and (two_turns or explicit_work or approval_denial or multiplex)`:
  **4 PASS11 deselected47.08s**, two conversational turns, managed work, native
  approval denial and production multiplexing.
- Claude2.1.281, selector `claude_code and (two_turns or explicit_work or approval_denial or question_roundtrip)`:
  **4 PASS11 deselected40.83s**, two turns, managed work, denial and explicit question.
- These campaigns preceded the final guard against *unqualified* shared connections;
  the final guard has Windows/Linux production fixture evidence above.
- Pi native NOT_RUN by user; dedicated Claude attach native NOT_RUN. Pi0.85.1 is
  protocol-fixture qualification, not a claimed model campaign. Native control
  campaigns from the prior milestone are not counted as runs of this milestone.

## Next dependency

Finish immutable-SHA full regression and matrix audit, stress/performance evidence,
then build/reinstall0.2.0. Preserve explicit external/native limitations. No phase
or final gate is promoted merely because these selected tests passed.

Final UI selection: same isolated wrapper, pytest -q --tb=short tests/test_runtime_diagnostics_dashboard.py -k session_capabilities: 2 PASS7 deselected21.61s. Final screenshot evidence/p02-effective-capabilities.png inspected: labels and two-column capabilities readable, no overflow, managed work disabled while conversation remains available.
