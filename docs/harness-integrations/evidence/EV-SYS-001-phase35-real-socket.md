# EV-SYS-001 — Phase 3.5 verified against a REAL running server

Captured: 2026-09-20 14:17 -03
Commit: `3ca7470`
Verdict: all gates green. Two minor findings, both disclosed.

## Why this file is the important one

Every prior evidence file in this folder proves something about a COMPONENT. This one proves the
SYSTEM: a real `okto-nexus serve` process, on a real ephemeral TCP port, driven by a real httpx
client, spawning real harness binaries. The project's evidence rule explicitly rejects in-process
TestClient calls, and this satisfies it.

The verification script lived in the scratchpad, never in the repo. It reused the session-scoped
`real_server` fixture from `tests/conftest.py` (EV-INF-001).

## Captured sequence

1. `GET /api/v1/info` -> 200,
   `{"service":"okto-nexus","package_version":"0.1.10","schema_version":29,...}`
   `schema_version=29` confirms migration 029 applied at a REAL boot.
2. `GET /api/v1/harness/kinds` -> 200, four real connector classes constructed in-process with
   zero side effects, each reporting its OWN declared capabilities:
   `claude_code/stream`, `claude_code/attach` (`send_only:true`, `steer_timing:null`),
   `codex` (`multiplexes_sessions:true`), `pi` (`steer_timing:"NEXT_TURN_BOUNDARY"`).
3. `POST /api/v1/harness/sessions {agent_id:"adversarial-real-pi", kind:"pi", ...}` -> 200 in
   **0.88s**, spawning the REAL `/opt/homebrew/bin/pi` binary as a child of the real serve
   process. Response `{"session_id":"hsess_989f...","status":"RUNNING"}`.
4. `GET /api/v1/harness/sessions/{id}` -> 200, `live:true` (in-memory supervisor view).
5. `GET /api/v1/agents/adversarial-real-pi` -> 200, `metadata.harness_kind="pi"` — **D3
   registration confirmed against the real agents table**, so the existing target grammar
   addresses harnesses with no new mechanism.
6. `POST /api/v1/harness/sessions/{id}/close` -> 200 in 0.026s, `status ENDED`, `ended_at` set.
7. `GET .../sessions/{id}` again -> 200, `live:false`, served from the durable row (D10).
8. A second spawn against the REAL `codex` binary also returned 200/RUNNING, and `/api/v1/info`
   remained 200 immediately after — the server stayed fully responsive with two real harness
   children attached.
9. `ps aux | grep -E "pi-coding-agent|codex|bundle/cli.js"` after teardown: **zero matches. No
   orphaned children.**

## Migration idempotency (REG-07), on a real SQLite file

Not reasoned about — executed against `/tmp/okto_migtest/home1/nexus.db`:
- first `MigrationRunner(factory).apply()` on an EMPTY db -> `[1..29]`, creating
  `harness_sessions` and `harness_events` with the specified columns
- second `.apply()` on the same factory -> `[]`
- third `.apply()` from a BRAND-NEW `ConnectionFactory`/`MigrationRunner`, simulating a fresh
  process against an already-migrated file -> `[]`

## Independently reproduced numbers

- `timeout 900 uv run python -m pytest -q` -> **1810 passed, 4 skipped** in 138.81s
  (1753 baseline + 57 new tests across four new files; no regressions)
- `timeout 200 uv run python -m pytest -q tests/test_http_parity.py tests/test_import_boundary.py`
  -> 5 passed
- `uv run ruff check .` -> All checks passed
- A standalone check built BOTH `create_server(deps)` and `create_http_mcp_server(deps)` and
  diffed `list_tools()`: identical 8 harness tools on both transports (51 tools total) —
  verified independently of the test file's own assertions.

## Gate results

| Gate | Result |
|---|---|
| boots | true |
| parity_green | true |
| import_boundary_green | true |
| migration_idempotent | true |
| failure_isolated | true |
| polling_in_harness_path | **false** |
| connector_port_modified | **false** |
| persistence_gates_delivery | **false** |

`git diff fb12248` is EMPTY for `domain/harness.py` and for all four connector modules —
byte-for-byte unchanged. `ports.py` is 100 insertions / 0 deletions: two new repo Protocols and
two new optional `Repos` fields, no existing signature touched.

`grep -rn "time\.sleep("` across the supervisor, subscribers, all four connectors and the MCP
tools module -> **zero matches** (only docstrings explaining `SleepPollWaiter`'s deliberate
absence).

## Two minor findings, carried open

**F-01 (minor).** No single test narrates the exact D8 failure class end to end: a connector whose
`start()` succeeds and whose `send()` returns normally, but whose `events()` generator never
yields and never raises — a permanently wedged POST-START pump. Start-wedge, close-wedge and
events-raises are each tested explicitly. The mechanism is sound by inspection (`close()` never
joins the pump thread; `_claim_for_reap` pops unconditionally) and is implicitly covered by
`test_failed_and_wedged_opens_never_affect_an_already_open_session`, where a good connector's pump
sits blocked in `events()` for the whole test. But given that "looks alive, delivers nothing" is
this project's signature defect class, it deserves its own dedicated test.

**F-02 (minor).** `GET /api/v1/info` carries no explicit `harness` field; the only observable
signal is `schema_version` incrementing to 29. This matches the repo's convention — `features` is
built from `FEATURE_FLAG_FIELDS`, which are opt-in config flags, and agents/handoffs have no
dedicated `/info` field either. So this is convention-conformant rather than a regression, but a
literal reading of the Phase 3.5 exit criterion ("`GET /api/v1/info` reflects it") is satisfied
only indirectly.
