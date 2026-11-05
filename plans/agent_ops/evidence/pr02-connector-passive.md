# PR-02 — passive Connector diagnostics

Windows 11 `10.0.26300`, Python 3.13.1; Connector `0.0.12`, Core `0.0.14`.
Connector source commit: `849f295` on `feature/v0.0.12`.

Standard `status`, `logs` and default `doctor` resolve the selected root without
creating it, its vault or a state lock. State and proxy inspection use a bounded
read of an existing atomic snapshot. Mutations retain their canonical writer
lock; diagnostics do not migrate, repair or overwrite the snapshot. Missing,
unreadable, invalid and newer-schema state remain distinct.

Status queries only authenticated, version-correlated live IPC, and preserves
starting, unknown, failed and degraded lifecycle facts instead of reporting a
stopped daemon. JSON includes the existing lifecycle observation. Unknown local
readiness returns exit 3 in summary, verbose and JSON modes. Server status still
uses existing credential references and read-only requests. Both that path and
explicit doctor probes honor recorded restricted-file consent; neither creates
the vault or grants fallback approval. Doctor's keyring count remains unknown
when enumeration is unavailable, and its output uses the existing redactor.

Logs read at most 256 KiB per poll, close the handle before waiting, preserve
partial records and discard oversized records above 16 KiB without exposing
unredacted fragments. JSON Lines reports missing/unavailable logs, rotation and
truncation separately from log records. Non-follow access failure returns 3;
follow reports the uncertainty and continues. Missing logs do not imply absent
work. Existing 2 MiB rotation and three backups remain in place.

Native tests exposed Windows `os.replace` rejecting an open destination even
with delete-sharing enabled. The state writer now retries permission denial
for at most one second, preserving the old snapshot on persistent failure.
The reader remains bounded and has no mutation lock. Tests cover an overlapping
reader/writer and preservation after permanent denial. Rename during a shared
log read was also checked on this Windows host.

## Validation

- **77 source tests passed** covering diagnostics, log bounds/redaction,
  doctor/probe consent, state concurrency, proxy behavior and passive discovery.
- **59 tests passed with the wheel installed in a fresh venv outside the
  checkout**. Copied tests include all new diagnostic cases, actual subprocess
  status/logs/default-doctor against an absent instance, and three concurrent
  daemon starters followed by reuse, restart and canonical drain. The actual
  doctor CLI uses an empty discovery environment and no identities or provider
  credentials. Unit state tests stub inventory to avoid scanning personal
  harness installations; the real CLI test does not stub discovery.
- Imports of Connector and Core were asserted under the fresh venv's
  site-packages. All **111 Connector Python payloads** in the final wheel match
  source without missing/extra files. The existing Core wheel is unchanged.
- Ruff passed for every changed Python file; `git diff --check` passed.

Source invocation:

```text
python -m pytest tests/unit/test_passive_diagnostics.py tests/unit/test_cli_diagnostics.py tests/unit/test_log_reader.py tests/unit/test_doctor_contract.py tests/unit/test_doctor_live_probe.py tests/unit/test_doctor_platform_support.py tests/unit/test_state_store.py tests/unit/test_proxy.py tests/unit/test_discover_diagnostics.py -q --tb=short
```

Installed invocation: `python -I -m pytest tests -q --tb=short`, with copied
diagnostic/doctor/state tests plus `test_detached_service_lifecycle.py` and
`test_passive_cli.py`; pytest asyncio mode is auto. The temporary venv is
`C:\Users\jpamb\AppData\Local\Temp\r3-passive-dydjrz0g\venv`.

Evidence: `pr02-connector-passive.xml`, `pr02-connector-passive-installed.xml`,
`pr02-connector-passive-wheel.json`; Nexus CI manifest and candidate wheel are
coordinated. No source Core change or additional version bump was needed.

## Remaining acceptance

SVC-10/11 and PR-02 remain IN_PROGRESS. This verifies the Connector passive
diagnostic subset, not the complete lifecycle or productive M1 acceptance.
General definition/context reconciliation, interrupted launch recovery and
controlled upgrade still need work. Native registration/login/logout/crash,
provider work and real POSIX qualification remain NOT_RUN. The previously
prepared native campaign remains awaiting authorization and still references
its original immutable installed candidates; no task was registered here.

No state schema, public Core contract or provider authorization changed. Revert
this diagnostic milestone only after applying the existing lifecycle/drain
rules if changing an active installed executable. There is no data migration
or destructive rollback in this change.
