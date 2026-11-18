# SI-004 — native integration preparation

Scope is static inspection of Core `497ee2b7a14b99c50cba97eac74f3b00d4863f26`,
Connector `a4d510080d7a685fa442a4c5c30419952589fe04` and primary upstream
documents. The Core wheel consumed by Nexus is version 0.0.14 with SHA-256
`ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5`.
States below describe inspected code and proposed proofs. The installed
harness fingerprints, process and user identity tests, and native acceptance
scenarios remain unexecuted.

## Codex

Core's `native/adapters/codex.py:248` owns one child stdio JSON-RPC
transport and correlates requests. The adapter multiplexes threads on that
transport (`:598`) and validates the exact thread and pending/active turn
at launch and at control (`:700`, `:909`, `:935`, `:953`). The existing
saved-resume seam requires the requested thread ID, checks the returned ID,
refuses a non-idle active/error thread and allocates a Core session mapping.
Resume on an already mapped thread is refused. This path is distinct from
attaching a viewer to the existing mapping.

The vendored file `native/codex_app_server_0_157_0.schemas.json` hashes to
`2719fccd25a97a7ce355497ca5e9123a63f6dce7f9f83724a5b73fd927811f59`.
It contains `thread/read`, `thread/resume`, `thread/unsubscribe`,
`turn/steer` and `turn/interrupt`. The adapter's older comment references
0.144.6. Both are historical evidence, distinct from the installed executable.

**Candidate.** OpenAI documents `codex resume <exact-thread-id>` with
`--remote` via WebSocket or Unix socket. First validate the actual TUI
handshake against a synthetic, scoped server. Record the selection/read
methods the frontend needs and confirm that omission of an exact ID cannot
start a thread. Implement a version-specific frontend gateway on the same
Core-owned engine, with bounded, authorized reads, isolated JSON-RPC IDs,
and typed mutations handed to the current Nexus admission path. Keep the
host subscription independently of viewers. Forwarding a viewer's
`thread/unsubscribe` over the owner connection could unload the thread
when it becomes idle. Treat new thread, fork, context change, config writes
and unrelated engine discovery as distinct capabilities to reject by default.
Documented remote mode is a candidate for the native frontend. A second
app-server, generic engine token or directly routed `turn/start` would break
Core ownership and auditing. [Codex App Server](https://learn.chatgpt.com/docs/app-server)
and [Codex developer commands](https://learn.chatgpt.com/docs/developer-commands).

## Pi

Core `native/adapters/pi.py:685` owns one RPC process per session. It uses a
native prompt and steer at the next boundary, guards post-abort work until
`agent_settled` and interprets that event as the final boundary
(`:169`, `:183`, `:1001`, `:1041`). Plain `agent_end`, timeout and an
accepted abort leave work eligibility unproved. Keep the ordinary Nexus input
in the Server's durable queue until a full boundary. Pi's `follow_up`
and steer may enter distinct native queues, and raw prompt can invoke
extensions or templates. The SDK documents that disposal aborts work
and that branch, switch and fork replace the active session.
[Pi RPC](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/rpc.md),
[RPC commands](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/rpc-commands.md),
and [Pi SDK](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/sdk.md).

**Candidate.** Current primary source exports `InteractiveMode`.
Its constructor accepts a native runtime and an optional `Terminal`
implementation. A version-pinned hosted Pi mode could keep one
`AgentSession` and the real renderer inside the owner, with the terminal
adapter surviving absence of viewers. Current TUI code also has direct
session mutations, signal handlers and shutdown paths that dispose the host
and exit. Terminal injection alone grants neither semantic interception nor
safe detach. A bridge must arbitrate those paths, prevent native/frontend
double-queue delivery and keep viewer EIO/EOF out of the owner shutdown
path. Existing stdio RPC is a different mode. Launching Pi again on the same
session file would be a second engine, regardless of file continuity.
[Pi SDK exports](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/src/index.ts)
and [Pi native interactive implementation](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/src/modes/interactive/interactive-mode.ts).

## Claude Code

Core `native/adapters/claude_code_stream.py:167` starts the CLI using
print mode and stream-json in/out. The adapter owns the stdin channel,
sends structured user messages and implements steer by reserving replacement
slot, interrupting the active turn and sending the replacement
(`:551`, `:570`, `:610`). It refuses controls in the pre-generation
requesting window. Closing stdin drains/exits the engine (`:669`), and native
permission responses are independently generation-bound (`:1024`).

**Candidate.** Anthropic documents `claude attach <id>` for workers owned by
its background supervisor. Establish a separate test mode that creates a
governed worker from the start, keeps its scope and CWD, and uses only its
exact ID. An already running print/stream-json session has no demonstrated
handoff to that supervisor. Current documentation says that even an explicit
`--resume <id> --bg` may create another ID. Refuse that fallback and any
scope change. A supervisor may restart workers in some cases. Record process
birth and generation to distinguish resume of saved conversation from live
reattach. The supervisor can perform separately billed row summaries, so
opening its agent view or backgrounding a prompt is outside the no-model
inspection. The central unresolved integration is interception/audit of
native keystroke effects through Nexus, including tool authorization and may-
have-executed recovery. Keep current stream-json workers intact while proving
a separate hosted bridge or a verified idle transfer.
[Claude Code CLI](https://code.claude.com/docs/en/cli-reference)
and [Claude Code agent view](https://code.claude.com/docs/en/agent-view).

## Host, presentation and proof boundaries

Connector already owns Core through `services/core_host.py:123` and
`daemon/app.py:318`. Its outbound NXL lane publishes durable, Core-journaled
events and uses authenticated binding tickets. The scopes in
`services/r4_tickets.py:11` are executor scopes. They do not confer human
terminal access. The future presenter should use an independent, short
credential scoped to person, exact session/owner generation, one writer
epoch and capabilities. Revalidate on effects, not just initial handshake.
Use a bounded presenter buffer and host-controlled worker I/O. For native
PTY modes, a Windows host must own ConPTY and service input/output independently.
The client only owns its view. Verify close-window behavior in addition to
synthetic disconnects. Keep remote qualification separate.
[Microsoft ConPTY architecture](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session).

## Proposed probe scope, pending consent

Run only bounded argv invocations with an exact resolved command under a new
temporary profile, empty project, no credential variables, no user settings,
and no payload from stdin. Record launcher and actual binary/package bytes
and hashes, OS, each command, redacted output and observed process exit. For
Node/PowerShell shims, pin the resolved runtime and package entry as well as
the shim. Use an explicit subprocess path and an allowlist for required OS
components. No login, model request, agent view, native session creation,
installation, arbitrary local config changes or existing daemon access is in
this scope.

| Harness | Finite no-model probes, once authorized | Observe |
|---|---|---|
| Codex | `--version`, `--help`, `resume --help`, `app-server --help`, then `app-server generate-json-schema --out <own-temp>` if advertised. Include experimental schema separately only if advertised. | Exact `--remote`/resume parser, transport support, event/approval shapes, thread and turn fences. |
| Pi | `--version`, `--help`, static installed package metadata and public SDK declarations. | Actual package identity and exports, native terminal injection seam, RPC command and event version. |
| Claude | `--version`, `--help`, and `attach --help` if advertised. | Native background attach parser and documented version-specific behavior. |

After those probes, first exercise a synthetic frontend handshake, bounded
disconnect and wrong-scope rejection. For native proof, request a separate
named candidate and budget. Require the same runtime tuple, engine birth,
native thread, owner epoch and original active turn before/after viewer exit.
Obtain durable completion evidence with zero viewers, then reattach and
compare transcript/turn identifiers. Exercise unauthorized second writer,
same-name sibling, stale target, lost response and read-only observer.
Use a separate isolated root per adapter and platform. Recording these gates
does not mark SI-T-G01/G11/G12/G16 or SI-T-I06 as passed.
