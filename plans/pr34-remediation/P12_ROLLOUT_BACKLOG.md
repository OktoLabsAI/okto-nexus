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
