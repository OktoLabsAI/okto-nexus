# PR-01 increment: Server exclusion before bootstrap

Scope: SVC-02 lifetime exclusion and prerequisite startup ordering; the full
SVC-01…04 lifecycle milestone remains in progress.

Implemented OS-held nonblocking guard files for canonical home and DB paths,
generation-tagged diagnostic metadata, fail-closed legacy PID recovery, and
lock acquisition before bootstrap/migrations. Never unlink guard inodes; never
kill by historical PID; heartbeat age does not transfer ownership. Failure
releases any acquired locks, and a prior generation cannot remove new metadata.

Windows 11 / Python 3.13.1:

- `rtk proxy .venv/Scripts/python.exe -m pytest tests/test_serve_lock.py tests/test_serve_args.py tests/test_import_boundary.py -q`: 27 passed (`pr01-locks.xml`). Includes two real Python contenders, exactly one owner, abrupt owner exit without release, successor acquisition, stale live heartbeat refusal, legacy unknown/reused PID refusal, canonical home aliases, shared DB across homes and bootstrap-not-called assertions.
- `rtk proxy .venv/Scripts/python.exe -m pytest tests/execution_r4/test_server_signal_shutdown.py -q`: 6 passed (`pr01-foreground-shutdown.xml`). Existing real foreground-process shutdown cases preserve HTTP/store lifetime until inventory ownership drains, including signal-first/HTTP-first and startup signal cases.
- `rtk proxy ruff check src/okto_nexus/adapters/outbound/service_manager src/okto_nexus/adapters/inbound/http/lock.py tests/test_serve_lock.py scripts/check_agent_ops_ledger.py scripts/measure_agent_ops_baseline.py`: passed.

The old test that simulated death solely by changing mtime was replaced: it
encoded the behavior R3 forbids. New tests use real process exit for that proof.
No provider, persistent OS service, login/logout, suspension or reboot campaign
was executed. POSIX implementation has not been executed in this run. Source-level
tests are not claimed as installed-wheel or automatic-start acceptance.

Also normalized the frontend HTML entrypoint through source newline attributes
and regenerated it with Vite. The previous build's CRLF/CRCRLF whitespace was
reported by `git diff --check`; this is an artifact reproducibility correction,
not a UI behavior change.

Compatibility: preserve ServeLock API/constants and foreground command. Existing
legacy metadata is conservatively reconciled. No schema/NXL changes, migration,
grant renewal or Connector/Core behavioral changes. Rollback requires stopping
the new Server first; do not downgrade while its OS guard is held. Preserve
canonical database/journals and uncertain outcomes. Next: SVC-01/03/04 facade,
topology resolution, background start/reuse and instance-correlated readiness.
