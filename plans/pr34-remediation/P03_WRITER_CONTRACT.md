# Store-wide writer contract

Parent: `f2222fbd99a1c10797690f6ffad2970f0d71c530`; implementation in this commit on `feature/v0.2.0`. Schema 057, MCP surface 50, identity reference 17. Final gate NOT PASSED.

## Reproduction and correction

The authenticated, feature-OFF stdio producer in P11_CUTOVER_AUDIT.md committed an unread delivery without a transport reservation while the feature-ON serve owner was active. The acceptance regression reproduced this as 1 FAIL (27.12 s), before implementation.

Migration 057 introduces a persistent singleton writer contract. The owner claim activates version 1 and its admission mode atomically with the owner epoch. SQLite triggers fence incompatible connections, including a connection opened before activation. Message admission additionally requires the producer mode to match the store mode. ConnectionFactory declares version compatibility and registers its mode only after obtaining the write lock. Owner settings changes update the mode in the same transaction, fenced by owner identity, epoch and live lease. Disabling admission retains the version fence and history; it does not reopen the store to old writers.

The markers are connection compatibility declarations, not authenticated identities or a defense against arbitrary direct database access. Existing request authorization remains mandatory. Unknown future contract versions refuse ownership without downgrading the store. No network, process, model or secret resolution occurs in these transactions.

MigrationRunner now uses sqlite3.complete_statement so trigger bodies stay intact. The first implementation failed on an incomplete trigger statement; the corrected rollback regression injects a failure after the real migration body and verifies no table, trigger or ledger entry survives, then retries successfully.

Operator diagnostics use EndpointService.diagnostics from both REST `/api/v1/harness/diagnostics` and MCP `harness_list(view="diagnostics")`. Ordinary callers are denied. CONFIG_ERROR distinguishes runtime_writer_incompatible from runtime_writer_mode_mismatch; neither requests automatic replay.

## Validation

All shell commands use the `rtk` prefix. Windows commands below ran from the main repository unless explicitly stated. Selection results are not aggregate full-suite results.

- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_writer_contract.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_handoff_recovery.py tests/test_runtime_relay.py tests/test_runtime_result_correlation.py`: **66 PASS**, 230.82 s, one known Starlette warning.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_writer_contract.py tests/test_feature_flags.py tests/test_frente1_resources.py tests/test_runtime_endpoints.py tests/test_import_boundary.py`: **83 PASS**, 70.13 s, one known Starlette warning. Before late MCP diagnostics parity addition.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_writer_contract.py tests/test_runtime_admin_surfaces.py`: **16 PASS**, 32.63 s, including REST/MCP parity and authorization.
- Detached development worktree at parent bdb1ca6, before integration: `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_writer_contract.py tests/test_runtime_operation_reconciliation.py -k "writer or migration"`: **7 PASS**, 17 deselected, 19.71 s. An earlier broader run was 52 PASS / 1 FAIL due to an obsolete expected migration list; updated to include 057.
- Linux development worktree: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_nexus_writer_fence_worktree -- /var/tmp/okto-writer-fence-xizu54r2/bin/python -m pytest -q --tb=short tests/test_runtime_writer_contract.py tests/test_runtime_outbox.py tests/test_runtime_shutdown.py tests/test_runtime_restart.py tests/test_migrations.py tests/test_settings_api.py tests/test_connection.py tests/test_import_boundary.py`: **56 PASS**, 135.74 s, one Starlette warning. Collected before the late migration rollback and diagnostics cases; no Linux native provider campaign.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py f2222fb`: OFF 43 tools / 40448 resident characters; ON 51 / 47730. ON docstrings +13 characters; surface revision 49 to 50.

Native campaigns in the isolated development worktree, schema 057: approved local Codex 0.156.1 and Claude Code 2.1.281 each passed the production two-turn serve/MCP/inbox/outbox/journal flow. Evidence: `evidence/p03-native-writer-codex.json`, `evidence/p03-native-writer-claude.json`. Commands: `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=<unique disposable directory> tests/test_runtime_native_campaign.py -k "two_turns and codex"` (1 PASS / 14 deselected, 13.87 s), and the same command with `two_turns and claude_code` (1 PASS / 14 deselected, 11.56 s). Explicit campaign selector/executable/auth-source configuration was used; temporary auth copies removed, no Nexus operator key passed to native children, no personal configuration or interactive session reused. These results qualify only the tested flows, not all capabilities. Pi and dedicated attach native remain NOT_RUN.

## Remaining dependencies

Combined SQLite/journal/artifact backup and restore, complete cutover/drain rehearsal, broader capability qualification, final immutable-SHA matrix and build/reinstall remain pending. The prior full suite remains recorded as 2296 PASS / 4 FAIL / 117 SKIP, not retroactively converted to PASS by these selections. Protected generated dashboard files and the unrelated policy fixture directory remain unstaged.
