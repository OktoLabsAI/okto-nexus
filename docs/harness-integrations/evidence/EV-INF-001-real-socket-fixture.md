# EV-INF-001 — Real-socket serve fixture (Phase 1)

Captured: 2026-09-20 09:36 -03
Commit:   3083fd2

First test infrastructure in this repo that binds a REAL socket. All later DoD
evidence depends on it.

- Fixture: session-scoped `real_server` in `tests/conftest.py`; boots real
  `okto-nexus serve` as a subprocess on an ephemeral port (bind :0, release, pass via
  OKTO_NEXUS_PORT). Never hardcodes 8202.
- Isolation: OKTO_NEXUS_HOME + OKTO_NEXUS_DB_PATH pinned to tmp_path_factory. The serve
  lock and default db_path both derive from home_dir, so isolating home isolates both.
- Readiness: polls GET /api/v1/info up to 30s; on timeout or early exit raises with the
  captured stdout/stderr attached.
- Teardown: SIGTERM -> 10s grace -> SIGKILL via os.killpg (start_new_session=True).
- Output: drained on daemon threads to avoid full-pipe-buffer deadlock.

```
$ uv run python -m pytest -q tests/test_real_server_fixture.py -x
3 passed in 0.78s

$ uv run ruff check .
All checks passed!

$ uv run python -m pytest -q      # full suite
1613 passed, 2 skipped in 65.04s
```

Regression check vs EV-REG-000 baseline (1610 passed, 2 skipped): +3, exactly the three
new self-tests. ZERO regressions. No orphaned server processes after the run.

## Caveat for Phase 3/4

Boot was sub-second, far faster than expected, most likely because embeddings are
degraded/stubbed on this machine. Work targeting a cold cache or `embedding_mode=local`
must budget more of the 30s readiness window and must not assume this generalises.
