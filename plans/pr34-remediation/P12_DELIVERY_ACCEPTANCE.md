# P12 — atomic delivery and recovery deadlines

Source `c9763741d7f976c84989ed9732bc8064dc43399b` plus the four final source/test SHA256 hashes in `evidence/p12-delivery-acceptance-index.json`. Branch `feature/v0.2.0`. No migration, native protocol or shared tool schema change.

## Reproduced defect and correction (F04 / P06)

The original coordinator bounded waits only by its ten-second heartbeat and retry deadlines. `recovery_seconds=1` did not wake recovery in one second. A committed PENDING delivery with its notification dropped remained unsent after3 seconds in the same live owner. Windows63762 terminal exit1: **1 FAIL8.63s**. The failure is the missing native write, after verifying a durable intent and unchanged wake generation; no new import or assumed mock behavior caused it.

An earlier coarse test used a15-second observation window and passed6 cases32.60s (Windows74507). This proved eventual recovery only and was not accepted as evidence for the configured deadline. Its manifest remains separate. Historical test generations have no recorded immutable test-file hash; final hashes are not retroactively applied.

`RuntimeDispatcher._run` now waits for the earliest recovery, heartbeat or retry deadline. After a store exception it postpones the recovery timer, preventing an expired timer from spinning. Wakes still interrupt the wait. Neither timeout nor recovery permits replay of an uncertain native send.

The previously constructor-only interval is wired through `NexusConfig` and the production `build_dispatcher`: `OKTO_NEXUS_RUNTIME_RECOVERY_INTERVAL_SECONDS` / `--runtime-recovery-interval-seconds`, integer1..86400, default30, CLI precedence, restart required. Zero is rejected rather than silently disabling lost-wake recovery. This startup setting does not add an MCP tool, permission, database setting or native status poll. Operational mapping is in `docs/harness-integrations/runtime-administration.md` and P05_P06_DURABLE_DELIVERY.md.

## Acceptance and evidence

- T-TX-01: fail after each real message, delivery, outbox and message.created write. The cut proves its row exists inside the writer transaction before raising. Message/delivery/outbox/events/causal root/link counts all revert, foreign keys remain valid, and no peer receives a send. A subsequent valid request succeeds once in the same composition.
- T-DISP-01: a real MCP message_create returns its committed message/delivery/operation while the peer write remains blocked by an event barrier. Transport is SENDING/ACK NONE; releasing the barrier produces one write.
- T-DISP-02: hold the actual owner just after an empty scan, drop the message's post-commit wake and inbox hint, then release it. The next wait returns the same generation and the committed intent dispatches before the3s test bound with1s configured recovery. No manual scan, wake or owner replacement occurs after commit.
- Configuration coverage exercises default/env/CLI precedence, invalid values, and actual production dispatcher construction. Store-error coverage observes a positive bounded wait after an injected writer failure.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_delivery_acceptance.py -q --junitxml=.git/pr34-evidence/delivery-acceptance-initial-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_delivery_acceptance.py::test_dropped_post_commit_wake_recovers_in_same_live_owner -q --junitxml=.git/pr34-evidence/delivery-recovery-deadline-red-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_delivery_acceptance.py tests/test_runtime_wake_generation.py tests/test_runtime_safe_retry.py tests/test_runtime_shutdown.py tests/test_config.py -q --junitxml=.git/pr34-evidence/delivery-acceptance-final-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_delivery_acceptance.py tests/test_runtime_wake_generation.py tests/test_runtime_safe_retry.py tests/test_runtime_shutdown.py tests/test_config.py -q --junitxml=.git/pr34-evidence/delivery-acceptance-final-linux.xml
rtk proxy ruff check tests/test_runtime_delivery_acceptance.py src/okto_nexus/config.py src/okto_nexus/application/runtime_dispatcher.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py
rtk proxy .venv/Scripts/python.exe scripts/live_client.py
rtk git diff --check
```

Final terminal exit0: Windows24588 **78 PASS86.46s**, Linux69701 **78 PASS96.86s**, including configuration, retry deadlines, lost-wake generation and coordinated shutdown regressions. Ruff and diff checks PASS. Isolated live MCP smoke exit0, `LIVE E2E RESULT: PASS`. Sanitized node manifests retain RED and both final runs; raw XML remains under `.git/pr34-evidence/` and captured logs/credentials are not committed.

This is internal SQLite recovery polling, not a no-polling claim for the whole hub. Synthetic peers qualify Nexus behavior; no provider/native version is newly qualified. A3s wall-clock bound includes scheduling and SQLite overhead, not a real-time SLA. No IO was introduced inside a writer transaction. Next: remaining original matrix, final committed-source suites and release/build/reinstall. Final gate remains NOT PASSED.
