# EV-CC-001 — External process injects a message into a live Claude Code session

Captured: 2026-09-20 09:04 -03
Substrate: `/tmp/cc-socks/<pid>.sock` (unix domain socket, one per INTERACTIVE session)

## Claim under test

An external, non-Claude-Code process — using only the Python standard library, with NO plugin,
NO MCP server and NO hooks — can deliver a message that a live Claude Code session receives.

## Method

A throwaway stdlib-only Python socket client connected to the `cc-socks` socket belonging to
the receiving session and wrote a marked message. The receiving session is the orchestrating
session of this feature work (`OktoNexus-dev [c99315]`).

## Result: CONFIRMED

The message was delivered and surfaced in the receiving session's conversation verbatim as a
cross-session message, attributed to another Claude session:

    IPC-PROBE-ND04D1: external stdlib-socket client (okto-nexus investigation),
    no plugin/MCP/hook involved.

This is a first-party observation: the receiving session is the one recording this evidence,
so delivery is witnessed directly rather than inferred from a log.

## Discovery evidence (transport)

`lsof -U`, with three interactive sessions live:

    2.1.274   3523 maheidem 13u unix 0x98bebade113b6e21 0t0 /tmp/cc-socks/3523.sock
    2.1.278  87357 maheidem  7u unix 0x80c46a1f855ca150 0t0 /tmp/cc-socks/87357.sock
    2.1.278  92180 maheidem  7u unix 0x7dbd54f1afd12557 0t0 /tmp/cc-socks/92180.sock

`ls -la /tmp/cc-socks/`:

    drwx------  5 maheidem wheel 160 20 set 09:00 .
    srw-------  1 maheidem wheel   0 17 set 09:05 3523.sock
    srw-------  1 maheidem wheel   0 20 set 08:25 87357.sock
    srw-------  1 maheidem wheel   0 20 set 08:33 92180.sock

PID 87907 was a `claude -p` non-interactive session and had NO socket: the listener is bound to
interactive sessions only. Nexus is a CLIENT of these sockets, so that does not constrain us.

## Wire protocol (recovered from the CLI bundle)

Newline-delimited JSON. An auth line is REQUIRED first. Verbatim from a log string inside the
shipped binary:

    [uds-messaging] Inject messages (auth line REQUIRED here):
    { echo '{"type":"auth","token":"'"$CLAUDE_CODE_MESSAGING_TOKEN"'"}';
      echo '{"type":"user","message":{"role":"user","content":"hello"}}'; } | socat - UNIX-CONNECT:${socketPath}

Other observed message types: `task-notification`, `poll-event`.
Send is fire-and-forget: the connection is accepted with no synchronous ack.

Socket path resolution: `${XDG_RUNTIME_DIR}/cc-socks/<pid>.sock`, falling back to
`/tmp/cc-socks-<uid>/<pid>.sock` when the path would exceed 103 bytes.

## Registry (what backs `ListAgents`)

Plain JSON, one file per PID, at `~/.claude/sessions/<pid>.json`:

    {"pid":92180,"sessionId":"...","cwd":"/Users/maheidem/Documents/dev/OktoLabsAI",
     "startedAt":1789903982261,"version":"2.1.278","peerProtocol":1,
     "peerFeatures":["notify_idle","reply_across_default_dirs","artifact_yield"],
     "kind":"interactive","tmux":"cc-OktoLabsAI-6682-3:@15.%15",
     "messagingSocketPath":"/tmp/cc-socks/92180.sock","name":"OktoNexus-dev","status":"busy"}

Every field `ListAgents` prints comes from here.

**An external process CANNOT register itself as a peer.** These files are written only by the
Claude Code process itself; there is no socket RPC to inject a registry entry. Nexus can send
INTO sessions, but cannot appear AS one in another session's `ListAgents`.

## Security properties (corrected)

An earlier draft of this file stated access control was filesystem permissions alone. That was
WRONG. Two mechanisms apply:

1. A per-session bearer token at `~/.claude/sessions/<pid>.<hash>.key`, mode `0600`, shape
   `{"peerToken":"...","procStart":"...","pidDomain":"darwin"}`. The auth line must carry it.
2. Kernel-level peer verification via `SO_PEERCRED`/`LOCAL_PEERPID`. The bundle describes the
   resulting value as "Kernel-verified pid... never from the payload", and `ownerUids` is
   checked. The connecting process's real uid/pid is attested by the kernel, not claimed.

The practical boundary is therefore: any process running as the SAME OS USER that can read the
token file can inject. That is a meaningfully stronger posture than bare file permissions,
though it is still same-user trust, not capability isolation.

Content injected this way renders to the model as a peer message, so it remains a
prompt-injection surface: anything Nexus pushes must be treated by the receiver as untrusted
data and must not be able to pose as system authority.

## Stability caveat

`cc-socks` is an UNDOCUMENTED, private protocol. No Anthropic documentation describes it. It can
change shape or disappear in any Claude Code release with no deprecation notice. This is the
decisive tradeoff against the supported MCP-notification path, and it is weighed in ADR 0004 D7.

## Related

- Wire format, method set and registry source: see the reverse-engineering report (in progress).
- The MCP-notification alternative failed in `-p` batch mode over both transports; see
  EV-CC-002 when the interactive test lands.
