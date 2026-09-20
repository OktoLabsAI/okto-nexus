# EV-REG-000 — Regression baseline (pre-change)

Captured: 2026-09-20 09:02 -03
Branch:   feature/harness-integrations
Commit:   4cb2161f9d2ad8ab86ce8bd32ae34c87161c7c74
Python:   Python 3.13.3
Command:  uv run python -m pytest -q

This is the reference the Phase 4 regression suite is diffed against.
Taken BEFORE any production code change on this branch.

```
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1610 passed, 2 skipped, 1 warning in 49.59s

[exited with code 0]
```
