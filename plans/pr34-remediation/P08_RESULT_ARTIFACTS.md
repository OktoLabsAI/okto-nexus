# Private result artifacts and storage boundaries

Parent `0490a05`, branch `feature/v0.2.0`, 2026-09-23. P08 remains IN_PROGRESS.

Migration 042 extends the existing artifact catalog with an optional explicit
reader list, and links runtime results to their published artifact and reserved
storage bytes. NULL preserves legacy visibility; an empty reader list denies
non-operator readers. Runtime artifacts restrict access to the source message
author and canonical runtime agent, in addition to the existing audience
snapshot. The authenticated operator retains administrative access. There is
no separate runtime artifact store or alternative artifact API.

Large captured text uses the existing `ArtifactStore`, `ArtifactService` and
catalog. A deterministic result-derived artifact ID permits retry without
duplicating files. Preparation verifies SHA-256 against captured text before
catalog publication. The file remains uncatalogued while approval is pending.
Canonical artifact permission/governance/guardrail checks run before storage
and again in the final UoW. Artifact catalog/event, message/delivery and result
publication link commit together. Truncated materialization is explicitly
labelled in both the reply and artifact metadata; an artifact does not restore
fragments beyond the existing materialization limit.

The shared artifact pipeline previously performed filesystem I/O while holding
a SQLite writer. A behavioral test reproduced this, then the implementation
moved storage between a read preflight and a short, revalidated catalog write.
Local storage flushes/fsyncs payload and manifest before directory rename,
with directory fsync on POSIX. New paths use private permissions where the OS
supports them. Cleanup checks resolved containment before recursive removal.
Windows machine power-loss qualification remains NOT_RUN; process-level tests
are not evidence of that stronger guarantee.

Runtime artifact bytes are durably reserved before filesystem effects: 64 MiB
globally, 16 MiB per logical recipient agent, 32 MiB per workspace. Endpoints do
not multiply an agent's allowance. Reservations include unpublished/uncertain
files and are not cleared speculatively on failure. Exhaustion preserves the
captured result and blocks artifact publication with QUOTA_EXCEEDED. Operator
recovery/collection of unpublished reservations and broader history retention
are the next operational dependency; do not edit counters or delete result
directories manually to bypass the accounting.

Publication now has one fixed worker/one slot rather than running filesystem
calls on the owner heartbeat thread. Busy work retains its slot; shutdown keeps
the owner and journal until it drains. A rescan flag preserves native terminal
wakes arriving during a publication scan, without an empty-scan busy loop.

Evidence:

- Storage-in-writer RED: `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_artifact_durability.py --tb=short`: 1 failed in 4.12s before
  correction, asserting real transaction state at `ArtifactStore.put`.
- Initial shared artifact/guardrail regression: 77 passed in 11.57s.
- File flush ordering, revocation during storage, failed fsync and artifact
  compatibility: 51 passed in 11.66s; later private-result integration selection
  62 passed in 46.51s.
- Initial Linux selection: 1 failed, 19 passed in 59.44s. The crash test had
  invoked a second private publisher concurrently with the production worker.
  It now waits for the injected cut in the actual worker instead.
- Separate native-wake behavioral RED: result stayed PENDING_AUTHORIZATION
  after a wake while publication was busy (1 failed in 9.59s). After the rescan
  fix, the same case passed in 5.38s.
- Final Windows command:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_artifact_durability.py tests/test_runtime_result_publication.py
  tests/test_runtime_result_correlation.py tests/test_runtime_shutdown.py
  tests/test_artifacts.py tests/test_guardrails.py tests/test_hitl.py
  tests/test_import_boundary.py --tb=short --maxfail=4`:
  **128 passed in 97.35s**, one existing Starlette/httpx deprecation warning.
- Final Linux command:
  `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus --
  /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q
  tests/test_runtime_artifact_durability.py tests/test_runtime_result_publication.py
  tests/test_runtime_shutdown.py --tb=short --maxfail=3`:
  **24 passed in 72.31s**.
- Ruff changed production modules: PASS. Native provider/model tests NOT_RUN
  for this unit; all process peers above are fixtures.

Remaining: orphan/reservation recovery and operator quota management, full
retention/cursor and machine crash qualification, explicit broadcast result
policy, P09 canonical work/bootstrap/native approvals, P10 causal continuation,
P11 complete administration/UI and P12 full matrix/build/install. No final gate
or complete-plan claim.
