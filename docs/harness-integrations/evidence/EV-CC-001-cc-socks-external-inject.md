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

## Security properties observed

Access control appears to be filesystem permissions alone (socket `0600`, directory `0700`).
Any process running as the same user can connect and inject. Content injected this way is
rendered to the model as a peer message, which makes it a prompt-injection surface: anything
Nexus pushes over it must be treated as untrusted data by the receiver and must not be able to
pose as system authority.

## Stability caveat

`cc-socks` is an UNDOCUMENTED, private protocol. No Anthropic documentation describes it. It can
change shape or disappear in any Claude Code release with no deprecation notice. This is the
decisive tradeoff against the supported MCP-notification path, and it is weighed in ADR 0004 D7.

## Related

- Wire format, method set and registry source: see the reverse-engineering report (in progress).
- The MCP-notification alternative failed in `-p` batch mode over both transports; see
  EV-CC-002 when the interactive test lands.
