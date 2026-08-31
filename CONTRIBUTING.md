# Contributing to Okto Nexus

Thank you for helping improve Okto Nexus. Use a focused branch and a pull
request for every change; the `main` branch is protected.

## Prerequisites

- Python 3.11, 3.12, or 3.13
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm when changing the dashboard

## Lightweight Python and stdio development

The development extra installs the test suite and the lightweight HTTP test
dependencies without the local embedding model:

```bash
uv sync --extra dev
uv run pytest -q
uv run okto-nexus
```

The final command starts the stdio MCP server. This path is appropriate when a
change does not need the bundled dashboard or real local semantic search.

### Live MCP smoke test

Run the live client after changing the MCP transport, coordination tools, or
SQLite persistence, and before opening a pull request that affects those paths:

```bash
.venv/bin/python scripts/live_client.py
```

On Windows PowerShell, use the virtual environment's Windows interpreter:

```powershell
.\.venv\Scripts\python.exe scripts\live_client.py
```

Unlike the unit suite, this script starts the real stdio MCP server and drives
an end-to-end two-agent flow through registration, sessions, messaging, event
delivery, handoff, artifact storage, and `shared.md` rendering. It uses temporary
home and project directories, then removes them on exit, so it does not touch
the user's `~/.okto_nexus` data. A successful run ends with
`LIVE E2E RESULT: PASS`.

## Full HTTP and dashboard development

Install the full `serve` extra when testing the HTTP transport, dashboard,
token accounting, or local embeddings:

```bash
uv sync --extra dev --extra serve
uv run okto-nexus serve
```

To build the dashboard into the Python package:

```bash
cd frontend
npm ci
npm run build
cd ..
```

The frontend build replaces the generated assets under
`src/okto_nexus/adapters/inbound/http/static/`. Do not edit those generated
files by hand.

For HTTP/dashboard development without the embedding model and its heavy
machine-learning dependencies, use `--extra serve-lite` instead of
`--extra serve`.

## Validation

Run the Python suite and lint checks from the repository root:

```bash
uv run pytest -q
uvx ruff check .
uv lock --check
```

There is no project formatter configuration. Keep edits focused and do not add
formatter, linter, or type-checker configuration as part of an unrelated
change.

When the dashboard changes, also run:

```bash
cd frontend
npm run build
```

Package-facing changes should additionally pass:

```bash
uv build
uvx twine check dist/*
```

Name explicit current-version artifacts when publishing; `dist/` can contain
older local builds.

## Pull requests

1. Branch from the current `main` branch.
2. Keep commits scoped and use a short imperative subject.
3. Add or update tests and documentation for user-visible behavior.
4. Describe validation performed and link related issues in the pull request.
5. Resolve review conversations and wait for the repository's required checks
   and approvals before merging.

Never commit API keys, session secrets, runtime databases, metrics output, or
private workspace content. Report security vulnerabilities using
[SECURITY.md](SECURITY.md), not a public issue.
