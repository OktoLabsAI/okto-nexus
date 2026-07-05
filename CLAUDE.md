# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Okto Nexus — a local Agent Coordination Bus. One process exposes an **MCP server** (`/mcp`), a **REST + SSE API** (`/api/v1`), and a **React dashboard** (`/`). A single SQLite file in WAL mode is the only source of truth — no broker, no background threads, no external services.

## Commands

Package manager is **uv** (`uv.lock` is committed); plain `pip` also works. Python `>=3.11`.

- Install (dev): `pip install -e ".[dev]"` — or global hub: `uv tool install ".[serve]"`
- Test: `python -m pytest -q` (pytest config sets `pythonpath=src`, so `src/` imports resolve without an install)
- Single test: `python -m pytest tests/test_config.py::test_name`
- Lint: `ruff check .` — **ruff runs on defaults; there is no project config. Do not add a ruff/black/mypy config without being asked.**
- Run the HTTP hub: `okto-nexus serve` → http://127.0.0.1:8202 (`--port`, `--host`, `--project-root`, `--log-level`)
- Run the stdio MCP server (dependency-light, legacy transport): `okto-nexus`
- Other CLI modes: `okto-nexus tail` (NDJSON event follower), `okto-nexus admin <cmd>` (e.g. `admin prune`)
- Frontend: `cd frontend && npm run build` (`tsc -b && vite build`); dev server `npm run dev` (port 5202, proxies `/api` + `/mcp` → 8202)

There is **no CI** (`.github/` does not exist) and **no pre-commit** — run the tests yourself before committing.

## Architecture — hexagonal (ports & adapters)

Single package `src/okto_nexus/`, strict layering that is **enforced by a test** (`tests/test_import_boundary.py`):

- `domain/` — pure, **stdlib only**. Never imports `sqlite3` or `mcp`.
- `application/` — use-case services + `ports.py` (Protocols). Also never imports `sqlite3` or `mcp`.
- `adapters/inbound/` — `mcp/` (FastMCP server + auto-discovered `tools/`), `http/` (FastAPI app + SSE + built dashboard in `static/`), `cli/` (`serve`, `tail`, `admin`).
- `adapters/outbound/` — `sqlite/` repos, `file/` store, `embedding/`, `tokenizer/`, `waiter.py`, `clock.py`.

When adding an MCP tool: drop a module under `adapters/inbound/mcp/tools/` exposing `register(server, deps)` — tools are auto-discovered, no central registry to edit. Keep the `mcp` SDK import lazy so domain/application stay import-clean. A test (`test_http_parity.py`) enforces the stdio and HTTP tool surfaces stay identical.

## Gotchas

- **The frontend builds INTO the Python package.** `frontend/vite.config.ts` sets `outDir` to `src/okto_nexus/adapters/inbound/http/static` with `emptyOutDir: true` — the build wipes and repopulates that dir, and it ships inside the wheel (end users never need Node). Don't hand-edit files under `http/static/` — they are generated.
- **Config is `OKTO_NEXUS_*`, precedence CLI flag > env > default, fail-closed** — a bad value raises `CONFIG_ERROR`, never a silent default. See `src/okto_nexus/config.py`.
- **State lives at `~/.okto_nexus/nexus.db`** (override with `OKTO_NEXUS_HOME` / `OKTO_NEXUS_DB_PATH`). `workspace_id = sha256(realpath(project_root))`; clients pass `project_root`, the server hashes it — reads/writes are workspace-scoped.
- **`serve` holds a lock** (`nexus.serve.lock`) — a second `serve` on the same home is refused until 60s of heartbeat silence. On Windows the `.exe` is also locked while running; stop running `okto-nexus` processes before reinstalling.
- Migrations (`migrations/00N_*.sql`) run automatically at bootstrap, before any tool registers.
- **Auth is same-machine trust (decision D5), not a bug.** On a loopback bind (`local_open`, default) a *keyless* REST/dashboard request is the reserved `operator` — `_require_operator()` (routes.py) admits `agent is None`. `/mcp` is never exempt (always key-gated). The only way to require keys is to bind off-loopback. Keyless loopback is fenced from browsers by `_loopback_trust_ok` (app.py): cross-origin `Origin` or DNS-rebound `Host` (via `Sec-Fetch-Site`) → `403 CROSS_ORIGIN_BLOCKED`. Destructive/config endpoints are operator-only (non-operator key → 403).
- Developed on **Windows / PowerShell** — venv is `.\.venv\Scripts\python.exe`.

## Conventions

- Single branch: `main`.
- Commit subjects: short imperative, usually category-prefixed — `Fix:`, `Docs:`, `Dashboard ...:` (conventional-commit forms like `chore(release):` also appear).
- Dashboard/UI text is written in **English**.
