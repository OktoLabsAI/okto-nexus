# EV-SYS-002 — SYS-01 (hub boot) and SYS-02 (all four connectors on one hub)

Captured: 2026-09-20, 17:58–18:06 -03. Real `okto-nexus serve` subprocess, real ephemeral TCP
port, real `pi`/`codex`/`claude` binaries. No TestClient, no mocks, no fakes. Driven with plain
`urllib`/`curl` HTTP calls against the running process — the same shape EV-SYS-001 established.

## FINDING (report, not fixed): the harness_open surface has no backend-selection parameter

Before any binary was touched, reading the composition root surfaced a real gap that is
load-bearing for this task's own safety constraint (`192.168.31.222` is off-limits):

- `HarnessSessionOpenBody` (`adapters/inbound/http/routes.py`) carries only `agent_id`, `kind`,
  `project_root`, `substrate`, `target_pid`, `role`, `metadata`, `notify_target` — no
  provider/model/env/command override.
- `_default_connector_factories()` (`adapters/inbound/mcp/tools/harness.py`, **not** one of the
  frozen files) constructs `PiRpcConnector(cwd=project_root)` and
  `CodexAppServerConnector(cwd=project_root)` — `provider`, `model`, `env`, `command` are all
  accepted by both (frozen) connector `__init__`s but the factory never passes them.
- `PiRpcConnector._build_argv` only appends `--provider`/`--model` when the constructor received
  them (`pi.py:710-717`), so a hub-opened `kind="pi"` session inherits **pi's own global default**
  (`~/.pi/agent/settings.json`: `"defaultProvider": "local-mac"`, which maps to `192.168.31.222` on
  this box — verified by reading the file directly, not assumed).
- codex is less exposed because its transport (`codex.py:254-261`) does
  `full_env = os.environ.copy(); if self._env: full_env.update(...)` — since the factory never sets
  `env` either, the codex child simply inherits the **`okto-nexus serve` process's own** full
  environment. Pi has no equivalent env-driven override (`--provider` is the only override path and
  it is argv-only, gated behind a constructor kwarg the factory drops).

**Net effect**: opening a `kind="pi"` session through the shipped `harness_open` surface, with zero
external configuration, sends real turns to `192.168.31.222` — forbidden by this task's own
constraints. This is a genuine composition-root gap (the on-demand surface never plumbs backend
selection through, unlike the boot-declared `HarnessBootSpec` path which does take an
already-constructed connector). It was **not fixed** (out of a test-writing task's scope, and
`tools/harness.py`/`routes.py` are not frozen but are still production wiring, not a test file);
it is reported here prominently as the rule instructs.

### How this evidence file avoided the box anyway

Two mechanisms, neither touching any source file, `~/.pi/agent/settings.json`, or
`~/.codex/config.toml`:

1. **codex**: `CODEX_HOME=<scratchpad>/codex_home` (containing the exact `_LIVE_CODEX_CONFIG` the
   codex INT agent already validated — `docs/harness-integrations/evidence` precedent,
   `tests/test_harness_codex_connector.py::test_live_against_real_codex_lan_box`) +
   `LANQWEN_API_KEY=unused`, set on the **environment of the `okto-nexus serve` subprocess this
   evidence file's own script booted** — inherited automatically per the code path above.
2. **pi**: a scratchpad-only PATH shim (`bin/pi`, never committed, same spirit as the pi INT
   agent's `tee_shim.py`). It is placed earlier on `PATH` than `/opt/homebrew/bin/pi`, **only in
   the env of the one `okto-nexus serve` subprocess this evidence run controls** (never the
   operator's shell PATH, never any other process on the machine, including this very Claude
   session). It resolves `pi`'s bare-name PATH lookup (confirmed empirically that `subprocess.Popen`
   honours the `env["PATH"]` kwarg, not the parent's own `os.environ`, on this Python
   3.13/macOS), injects `--provider zai --model glm-5.3` ahead of the connector's own argv
   (`--mode rpc --session-id <id>`), and relays stdin/stdout byte-for-byte to the real binary
   (spawned as a genuine child, not `exec`'d, so both directions can be logged with
   `time.monotonic()` timestamps — this doubles as the SYS-05 wire-trace tap for pi).

**Bounded smoke-tested BEFORE any turn was sent** (`get_state` is a local RPC probe — zero
inference, safe against the real binary):

```
$ timeout 40 python3 shim_smoke.py
got_response: {"type": "response", "command": "get_state", "success": true,
  "data": {"model": {"id": "glm-5.3", "provider": "zai",
                      "baseUrl": "https://api.z.ai/api/coding/paas/v4", ...}}}
--- trace_log ---
0.000000 SHIM_ARGV ['/opt/homebrew/bin/pi', '--provider', 'zai', '--model', 'glm-5.3',
                     '--mode', 'rpc', '--session-id', 'sys-shim-smoke-1789926960']
...
SMOKE OK: shim intercepted `pi`, injected --provider zai, real binary answered get_state.
```

Full trace: `EV-SYS-002-pi_shim_smoke_trace.log`. `baseUrl` confirms zai, not `.222`, **before**
this evidence file's server was even booted. Every subsequent pi spawn in this suite's own trace
(`EV-SYS-004-005-009-trace_pi.log`) starts with the identical `SHIM_ARGV ... '--provider', 'zai'`
line — the assertion that provider injection actually took effect was re-verified per-spawn, not
assumed once.

A `codex` and a `claude` PATH shim (pure relay, no argv injection — codex/claude need no backend
override) were built the same way, purely so SYS-05's wire trace could tap all three full-duplex
harnesses identically.

## SYS-01 — hub boots with harness support; `GET /api/v1/info` reflects it

```
$ timeout 10 curl -s http://127.0.0.1:53290/api/v1/info
{
  "ok": true, "data": {
    "service": "okto-nexus", "package_version": "0.1.10", "schema_version": 29,
    "trust_mode": "open",
    "features": {"feature_trace": false, "feature_hitl": false, "feature_verification": false,
                 "feature_dag": false, "feature_memory": false, "feature_health": false,
                 "feature_replay": false}
  }
}
```

`schema_version=29` — confirms migration 029 (`harness_sessions`/`harness_events`) applied at a
REAL boot, exactly as EV-SYS-001 documented. **Stated honestly, matching EV-SYS-001's F-02**:
there is no explicit `"harness": true`-shaped field in `/info` — `harness` is not a
`FEATURE_FLAG_FIELDS` entry by this repo's own convention (an opt-in config flag), and
`schema_version` incrementing is the only observable signal, same as agents/handoffs have no
dedicated `/info` field either. The task brief's own phrasing anticipated exactly this and asked
for the honest statement rather than an invented field — given here.

```
$ timeout 10 curl -s http://127.0.0.1:53290/api/v1/harness/kinds
{
  "ok": true, "data": {"harnesses": [
    {"kind": "claude_code", "substrate": "stream",
     "capabilities": {"send_only": false, "steer_timing": "IMMEDIATE", ...}},
    {"kind": "claude_code", "substrate": "attach",
     "capabilities": {"send_only": true, "steer_timing": null, "observes_session_end": false}},
    {"kind": "codex",
     "capabilities": {"send_only": false, "steer_timing": "IMMEDIATE", "multiplexes_sessions": true}},
    {"kind": "pi",
     "capabilities": {"send_only": false, "steer_timing": "NEXT_TURN_BOUNDARY",
                       "interrupt_requires_settle_wait": true}}
  ]}
}
```

Four real connector classes, capabilities read straight off each one — matches the frozen
`HarnessCapabilities` values in `domain/harness.py` docstrings exactly.

**Verdict: SYS-01 PASS** (with the F-02-precedent honesty note carried forward).

## SYS-02 — ALL connectors attach to ONE running hub simultaneously

One `POST /api/v1/harness/sessions` per kind/substrate, back to back against the SAME hub process
(pid recorded in `EV-SYS-002-open_all_results.json`):

| kind/substrate | session_id | status | open latency |
|---|---|---|---|
| pi | `hsess_066f968502bd44f48aa49f100878550c` | 200 RUNNING | 1.027s (real handshake) |
| codex | `hsess_d7c8c068a0624872a79717094feba6dd` | 200 RUNNING | 0.444s |
| claude_code/stream | `hsess_c7f18beb4af34fdd92e9044ef1ed56b0` | 200 RUNNING | 0.005s (process spawn only, no handshake block) |
| claude_code/attach | `60906.a6ca...` | 200 RUNNING | 0.003s |

The attach substrate's `target_pid=60906` is a **dedicated, throwaway** interactive Claude Code
session, spawned by this evidence run in its own `tmux` session (`sys-harness-attach`) specifically
for this test — verified NOT to collide with any of the three pre-existing real interactive
sessions already running on this machine (pids 92180, 3523, 87357 — genuine ongoing work, never
touched).

D3 registration, checked against the real `agents` table for all four:

```
$ curl -s .../api/v1/agents/sys_pi_agent        -> metadata.harness_kind = "pi"
$ curl -s .../api/v1/agents/sys_codex_agent     -> metadata.harness_kind = "codex"
$ curl -s .../api/v1/agents/sys_cc_stream_agent -> metadata.harness_kind = "claude_code"
$ curl -s .../api/v1/agents/sys_cc_attach_agent -> metadata.harness_kind = "claude_code"
```

All four `is_active:true`, all registered via the SAME `AgentRepo.upsert` path `agent_register`
itself uses (D3) — full output in `EV-SYS-002-open_all_results.json`.

**Verdict: SYS-02 PASS.** Full raw open responses: `EV-SYS-002-open_all_results.json`.
