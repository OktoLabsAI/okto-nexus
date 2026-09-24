# P12 — activation backlog and single-executor cutover

2026-09-24, isolated migration worktree based on
`58ca69b1afbb04c4272717d8e0028dcb36166e6f`. Main Linux regression70522 is still
running; this new acceptance test is not integrated yet. Final gate NOT PASSED.

T-MIG-05/06 now have a combined exact test:
`test_runtime_rollout.py::test_activation_does_not_replay_old_unread_and_legacy_notifications_do_not_duplicate_transport`.

The disabled production socket app first creates three canonical unread messages.
A new explicitly enabled production app lifespan opens the same disposable store.
Operator REST APIs configure an isolated profile and endpoint; MCP opens it.
The enabled app uses actual production connector factories, a real owned Python
Codex-shaped pipe peer and the approved profile command, not an injected factory.
The enabled app uses Starlette TestClient transport; it is not a second OS serve
process. Process-kill and multi-process writer gates remain separate.

Opening/scanning creates no intents for old unread deliveries. One new canonical
message produces one durable result. The test repeats both new and historical
post-commit notifications through the real notifier and scans again. Production
supervisor has no executable legacy callback subscription. After durable close
and confirmed child exit, the peer's stdin trace has exactly one turn/start,
containing the new marker and no old marker. Checking after process cleanup
avoids claiming no duplicate based on a short sleep. Full original old delivery
rows remain unchanged; outbox contains only the new message.

No production correction was necessary; this closes an exact acceptance coverage
gap. No provider, ambient login/config, real user store or historical real event
replay was used. No operating-system migration/reverse SQL or manual endpoint
database insertion was required.

```text
rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_rollout.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_nexus_migration_acceptance_worktree /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_rollout.py
rtk proxy ruff check tests/test_runtime_rollout.py
```

First command cwd: D:/Projetos/Techridy/okto_nexus_migration_acceptance_worktree.
Windows execution94777:1 PASS7.90s, exit0. Linux39527:1 PASS11.60s, exit0.
Both emit the existing Starlette/httpx TestClient deprecation warning. Ruff PASS.
Content hash is recorded in evidence/p12-rollout-backlog-worktree.json.

Next: integrate this sixth reviewed worktree path after main full70522 ends.
Active rollback with SENDING/accepted attempts and pending journal (T-MIG-07),
retention/deactivation (T-MIG-09), crash/load/performance and remaining matrix
requirements are not certified by this activation test.

## Active disable and delayed native facts — isolated continuation

The same module now also tests T-MIG-07 with two explicit cuts: accepted turn
with terminal projection pending, and an actual native write whose transport
call subsequently raises while acceptance/terminal are already journaled. The
operator disables the feature through REST. New MCP send is denied, the store
writer admission flag is OFF, and canonical pull cannot claim the reserved
delivery. Projection resumes without another transport attempt or publication.

Execution history (Windows, same module command/cwd above):

- 4963: 1 FAIL / 1 deselected, 14.60s. The test incorrectly required BLOCKED;
  OFF deliberately suspends publication in PENDING_AUTHORIZATION. Corrected the
  assertion to check preserved capture and no publication. No product change.
- 67175: 2 PASS, 10.85s; Linux22175: 2 PASS, 14.58s.
- 62693: 2 PASS / 1 FAIL, 19.88s. New sending-cut fixture held projection before
  dispatch and thereby blocked scheduling. Moved its barrier into the active
  native send call; this was a test instrumentation error.
- 56925: 2 PASS / 1 FAIL, 23.24s. Genuine behavior RED: after the call raises,
  OUTCOME_UNKNOWN rejects the exact already-captured current-owner acceptance
  and terminal. The terminal remains in raw history without operation linkage.
- 34522: 3 PASS, 14.34s after narrow projector correction. One existing
  Starlette/httpx deprecation warning; no native provider used.

`SqliteRuntimeJournalRepo._project_attempt` now permits exact current-owner
OUTCOME_UNKNOWN observations to resolve uncertainty, retaining the existing
session/connection/attempt/owner checks, acceptance requirement for a terminal,
and explicit reconciliation branch. Old-owner observations still require the
frozen recovery boundary; no retry, new transport call, or handoff completion
is authorized. No schema migration or public contract change is necessary.

Expanded Windows32259/Linux90306 completed:56 PASS238.46s /56 PASS248.55s, both exit0 and one existing deprecation warning, using:

```text
rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_rollout.py tests/test_runtime_result_correlation.py tests/test_runtime_restart.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_commands.py tests/test_runtime_work_results.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_nexus_migration_acceptance_worktree /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_rollout.py tests/test_runtime_result_correlation.py tests/test_runtime_restart.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_commands.py tests/test_runtime_work_results.py
```

This adds a seventh integration path, `src/okto_nexus/adapters/outbound/sqlite/runtime_journal_repo.py`.
The isolated implementation/tests remain uncommitted until the immutable main
Linux run70522 finishes. The earlier JSON hash documents the original activation
test only; it is not the source hash of these additional cases. Retention,
process-kill/load and full final gate remain open.

Final isolated source hashes and results: evidence/p12-rollout-disable-worktree.json. Ruff passed for the two changed files. Expanded selections include old-owner frozen-boundary rejection, explicit reconciliation, durable commands and managed result fencing. No main integration or final gate promotion yet.

Subsequent integration: full Linux70522 is terminal. Seven reviewed paths are now
in feature/v0.2.0; the detached checkout is historical. See
P12_MIGRATION_ROLLOUT_INTEGRATION.md for integrated qualification and current
status, superseding the earlier transfer-pending notes. Full58ca69b terminal
counts do not qualify the later projector correction.
