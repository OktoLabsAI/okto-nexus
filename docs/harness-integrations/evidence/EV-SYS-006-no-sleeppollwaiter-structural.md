# EV-SYS-006 — SYS-06: `SleepPollWaiter` is NOT in the harness path, asserted structurally

Two independent structural checks, neither a timing measurement (per the case's own instruction:
"asserted structurally, not by timing").

`sys06_import_closure.py` is scratchpad-only (never committed, same convention as the other SYS
evidence files) — its real captured output is inlined below.

## 1. Real transitive import-closure check (primary evidence)

Rather than a hand-rolled AST walk that could miss a dynamic import, this imports the harness
path's REAL entry points for real (letting Python's own import machinery resolve the whole
dependency graph), then inspects every `okto_nexus` module that import pulled in, parsing EACH
ONE's own top-level import statements for any reference to `waiter`/`SleepPollWaiter`:

```
$ timeout 60 uv run python sys06_import_closure.py
Transitive okto_nexus modules pulled in by the harness path entry points: 90
 - okto_nexus.application.harness_supervisor
 - okto_nexus.adapters.outbound.harness.subscribers
 - okto_nexus.adapters.outbound.harness.pi
 - okto_nexus.adapters.outbound.harness.codex
 - okto_nexus.adapters.outbound.harness.claude_code_stream
 - okto_nexus.adapters.outbound.harness.claude_code_attach
 - okto_nexus.adapters.inbound.mcp.tools.harness
 - okto_nexus.adapters.inbound.http.routes
 ... (90 total, full list in the script output)

Modules whose OWN import statements reference `waiter`/`SleepPollWaiter`: 0

SYS-06 STRUCTURAL CHECK: PASS - no module reachable from the harness push path imports
adapters.outbound.waiter or SleepPollWaiter, directly or transitively.
```

Entry points: the supervisor, the subscriber registry, all four connectors, the MCP harness tools
module, and the full HTTP routes module (which pulls in every SQLite repo the whole app uses,
including several unrelated to harnesses — the check is intentionally generous about what counts
as "reachable," making a false PASS harder, not easier, to get).

## 2. Secondary grep (the EV-SYS-001 precedent method, kept as a corroborating check)

```
$ grep -rn "time\.sleep(" src/okto_nexus/application/harness_supervisor.py \
    src/okto_nexus/adapters/outbound/harness/ \
    src/okto_nexus/adapters/inbound/mcp/tools/harness.py \
    src/okto_nexus/adapters/outbound/waiter.py
(zero matches in the harness modules themselves)

$ grep -rln "SleepPollWaiter" src/okto_nexus/
adapters/outbound/harness/{claude_code_stream,codex,pi,subscribers}.py   <- prose only, see below
adapters/outbound/sqlite/connection.py                                   <- the ONE real import
application/harness_supervisor.py                                        <- prose only
application/ports.py                                                     <- prose only
```

Every hit in the four connector modules and `harness_supervisor.py`/`ports.py` is **prose inside a
docstring or comment explaining that `SleepPollWaiter` does NOT appear** (each cited and quoted
inline in the modules' own text, e.g. pi.py:68 "so `SleepPollWaiter` (D1) has no reason to appear
and does not"). The only ACTUAL `from ..waiter import SleepPollWaiter` in the whole codebase is
`adapters/outbound/sqlite/connection.py` (`ConnectionFactory.change_waiter()`), which is not part
of the harness path — confirmed separately:

```
$ grep -n "change_waiter" src/okto_nexus/application/harness_supervisor.py \
    src/okto_nexus/adapters/outbound/harness/*.py \
    src/okto_nexus/adapters/inbound/mcp/tools/harness.py \
    src/okto_nexus/adapters/inbound/http/routes.py
(no matches — the harness path never calls ConnectionFactory.change_waiter())
```

**Verdict: SYS-06 PASS**, on two independent structural methods (transitive import-closure +
targeted grep/call-site check), neither involving a clock.
