# PR-04 participant foreground launcher — 2026-11-06

`okto-nexus participant launch` now selects the completed participant profile,
authenticates its existing vault credential and reviews the native executable,
physical project, current file bytes/access policy and client home selectors.
Apply revalidates those facts and starts the selected client in the foreground.
Only the child receives the dedicated environment variable; other participant
references are stripped from that child's copy. The caller's environment,
existing runtime/bindings/grants and Server identity are preserved.

Codex receives `--no-daemon`; arbitrary configuration files that the client would
not load are refused. Claude uses its normal project trust or an explicitly
selected `--mcp-config`. Native policies, provider login and other client
settings remain the client's responsibility. No prompt is sent by the launcher.

The private launch intent precedes spawn. Lost spawn/checkpoint replies retain
`starting` or `started` and cannot automatically respawn. Replaying the exact
approval reports that attempt; `--new` explicitly reviews a new one and retains
the previous process hints. Exit/PID and supplied environment never imply MCP
authentication, reload, participation or work.

## Validation

- [Source tests](pr04-participant-launch-source.xml): 19 passed, covering
  independent drift boundaries, exact approval, checkpoint loss, spawn failure,
  interruption, new intent, supported file locations, passive saved review,
  redacted errors and real subprocess environment delivery.
- [Installed tests](pr04-participant-launch-installed.xml): 74 passed outside the
  checkout with `python -I`, including launch, init, participant/managed doctor
  and HTTP-only CLI regressions. These overlap the source tests.
- [Wheel audit](pr04-participant-launch-wheel.json): 447 Python payloads and seven
  static assets byte-match source. Fresh build copy and fresh environment;
  unchanged Core 0.0.14 and Connector 0.0.12 candidate wheels.
- [Actual installed console](pr04-participant-launch-cli.json): missing profile
  reports the correct failure without creating a home directory.
- [Native cases](pr04-participant-launch-native.json): Claude Code 2.1.317 and
  Codex 0.166.0 each tested with present and absent references on Windows.
  Generated Core files and installed Nexus environment/context helpers were used.
  A synthetic HTTP MCP responder checked exact Bearer equality without recording
  the key. Present references authenticated initialize/list; absent references
  did not. Both negative cases still exited zero, demonstrating why an exit code
  cannot be treated as readiness. No key was found in campaign-owned files.

The [reproducible campaign](../campaigns/participant-environment.py) requires
explicit native executable paths and a new output directory. It isolates client
homes, uses random fixture credentials and dummy provider credentials, and sends
no user messages, `turn/start` or `tools/call`. Claude uses stream-json control
initialize/status, `--bare` and the explicitly selected strict MCP fixture.
Codex uses a trusted temporary project and an ephemeral app-server thread so its
project configuration is actually loaded. This is protocol-mode qualification,
not a full interactive terminal or GUI campaign. The control status request is
documented in the [official Claude SDK source](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/query.py).
Codex protocol schema and installed binary help were inspected locally.

## Corrections and limits

The initial source run used an incorrect Core Claude adapter identifier; it was
stopped and corrected to the registry's `claude_stream`. A subsequent policy
drift test updated a nonexistent fixture row, producing [five passes and one
failure](pr04-participant-launch-source-initial.xml). Inserting the explicit MCP
policy row corrected the fixture; no production authority bypass was involved.
An installed invocation initially named nonexistent test files and ran no tests;
the corrected invocation produced the 74-case report above. Codex's global MCP
status initially had no project entry; qualification was corrected to use the
ephemeral project thread without a model turn.

The campaign used a synthetic vault in application tests and a synthetic MCP
responder in native-client tests. It did not exercise the complete chain from a
real OS vault through an interactive real client to canonical Nexus cooperation.
There was no personal credential/configuration change, provider inference,
service registration, package publication or merge. Actual GUI/TUI behavior,
other builds/platforms, redirected native-client HTTP, vault qualification,
cleanup/compensation, cooperation and productive M1/M2 remain open. PR-04 and the
full R3 plan are still in progress.
