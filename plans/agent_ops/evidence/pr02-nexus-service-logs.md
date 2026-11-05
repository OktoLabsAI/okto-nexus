# PR-02 — passive Nexus lifecycle logs

Windows 11 `10.0.26300`, Python 3.13.1, Nexus `0.3.3`, Core `0.0.14`.

`ServiceLifecycle.logs` and `okto-nexus service logs --tail/--follow --json`
read bounded local diagnostics without bootstrap, transport inspection or any
start/stop operation. An absent home remains absent; a broken saved interpreter
does not prevent log access. Missing/unavailable logs retain explicit codes and
never establish process availability or the absence of work. Ctrl+C ends only
observation with exit 130.

The foreground Server opens `logs/service.jsonl` after acquiring instance
ownership. Detached and scheduled paths use this same entrypoint. Records contain
only timestamp, generation, supervisor, known lifecycle code/state and known
error code. Arbitrary exception/provider text, prompts and credentials are not
accepted by the writer or replayed by the reader. Existing runtime journals,
results and shutdown receipts remain authoritative.

The active log rotates at 2 MiB with three backups. Reads are capped at 256 KiB
and 1..10000 requested records, preserve partial lines until complete, withhold
malformed/unknown records and report truncation/observed rotation. A follow poll
closes its handle before sleeping. A slow reader can miss records moved to
backups; this is not a lossless event journal or a work-state reconstruction.
Logging I/O failure cannot reopen admission or change drain behavior.

## Evidence

- `pr02-nexus-service-logs.xml`: **49 passed, 2 POSIX skips**, covering the new
  reader/writer/CLI, existing lifecycle/argument controls, real concurrent Server
  generations, and existing foreground cleanup with owned harness fixtures.
- `pr02-nexus-service-logs-final.xml`: **12 passed** after adding rotation
  indication and the I/O failure case. Its first fixture attempt expected an
  empty file to rotate; Python intentionally skips that rotation, so the fault
  was never injected. Seeding one record made the test exercise the intended
  failure. No product assertion was weakened. The preceding affected run had
  47 passing tests and that one fixture failure.
- `pr02-nexus-service-logs-installed.xml`: **13 passed** against the final wheel
  installed with `serve-lite` and the pinned local Core wheel in a fresh venv.
  Test files were copied to the disposable package directory, isolated Python
  ran from outside the checkout, and `okto_nexus.__file__` was verified under
  the new venv's site-packages. This includes concurrent CLIs, launcher exit,
  reuse, restart, generation-checked drain and log reading after exit.
- `pr02-nexus-service-logs-wheel.json`: all **412** Python payloads match source
  byte-for-byte; no missing or extra Python files. The record includes SHA-256,
  installed import provenance and the main dependency versions.
- Ruff passes on changed Python files; `git diff --check` and the fixed-plan
  coverage validator are required before commit.

Commands used the existing Nexus development venv for source tests:

```text
python -m pytest tests/test_service_logs.py tests/test_service_inspection.py tests/test_service_start.py tests/test_service_process.py tests/test_serve_args.py tests/test_serve_harness_shutdown_reap.py -q --tb=short
python -m pytest tests/test_service_logs.py -q --tb=short
python -m build --wheel --outdir <disposable-directory>
```

After creating a fresh venv and installing the candidate with `serve-lite`, the
local Core wheel and pytest, the isolated package command was:

```text
venv/Scripts/python.exe -I -m pytest test_service_logs.py test_service_process.py -q --tb=short
```

## Limits and rollback

SVC-01/10/12 and PR-02 remain in progress. Standard doctor/passive diagnostics
beyond this command, remaining service controls/reconciliation/upgrades, actual
task registration/login/logout/crash/credential campaigns and productive remote
work are still open. No personal task, provider, credential, package publication
or merge was used. Existing harness tests use approved disposable fixtures.

This adds an operational file, not a database schema or NXL revision. Reverting
the reader/writer leaves retained logs inert and does not alter canonical work
state. Existing service shutdown/ownership rules continue to apply to rollback.
