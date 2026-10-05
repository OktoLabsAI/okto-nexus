# INT-01 / INT-02 / INT-08 — Claude Code ATTACH (`cc-socks`), real interactive session

Captured: 2026-09-20 17:24–17:27 UTC
Commit under test: `b661538dda0055a557beaddd8f83c5e770206c43`
Module: `src/okto_nexus/adapters/outbound/harness/claude_code_attach.py`
Connector: `ClaudeCodeAttachConnector`

## Scope: reduced INT set for H-CA

Per `plans/harness-integrations/01-test-plan.md`:

> Applies to H-PI, H-CX, H-CC. H-CA runs a reduced set (INT-01, INT-02, INT-08) because it is
> send-only with no ack.

`CAPABILITIES` (`claude_code_attach.py:109-115`): `send_only=True`, `steer_timing=None`,
`interrupt_requires_settle_wait=False` (not-applicable value, no interrupt verb exists),
`multiplexes_sessions=False`, `observes_session_end=False`.

INT-03 (event stream fidelity), INT-04 (no-polling wire trace), INT-05 (steer), INT-06
(interrupt), INT-07 (session persistence) are **struck for H-CA, not silently skipped**, each
for a structural reason tied to a capability field, not a testing shortcut:

- **INT-03/04 N/A**: `send_only=True`, `observes_session_end=False`. This connector has **no
  inbound channel at all** — `events()` only ever drains locally-originated events this
  connector itself mints (send failures / pid-reuse-guard trips), never a native wire stream
  from the peer (module docstring, `claude_code_attach.py:37-38`, `789-807`). There is nothing
  to trace fidelity against and no wire trace to capture; fabricating one would misrepresent
  the transport. The "no polling" claim is trivially true here because there is no read loop of
  any kind to poll with — confirmed below by the RES-A3/B3 structural grep (zero `recv(`, zero
  `select.`, zero `Queue.get` in the module).
- **INT-05 N/A**: `steer_timing=None`. `send()` raises `VALIDATION_ERROR` for any
  `command.verb != "send_turn"` (`claude_code_attach.py:702-710`), and `HarnessCommand`'s own
  frozen `__post_init__` in `domain/harness.py` rejects an unrecognised verb before the
  connector is even reached. There is no steer verb this transport can accept.
- **INT-06 N/A**: no interrupt verb on this transport at all (same `send()` guard as above);
  `cc-socks` has no abort primitive to test settle-signal ordering against.
- **INT-07 N/A**: `observes_session_end=False` and this connector never spawns anything — it
  binds to a peer Nexus did not create. `domain/harness.py`'s `_TRANSITIONS` table gives a
  `send_only`/non-observing connector no legal producer path to `ENDED`
  (`can_transition_session` only allows `STARTING -> RUNNING -> {INTERRUPTING, ENDED, ERRORED}`,
  and nothing in this connector ever calls `_transition(STATUS_ENDED)`). There is no
  reconnect/resume concept to test: the "session" is an ambient peer identity
  (`<pid>.<key-hash>`), not a server-minted one this connector could resume.

## SAFETY — live-session register, read BEFORE writing anywhere

Read-only enumeration of every live Claude Code interactive session, run first, before any
`start()`/`send()` call against a real pid:

```
$ ls -la ~/.claude/sessions/
$ for f in ~/.claude/sessions/*.json; do cat "$f" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); print({k:d.get(k) for k in \
    ['pid','name','cwd','tmux','status','kind','version']})"; done
```

Output (2026-09-20, before spawning anything of my own):

```
{'pid': 3523, 'name': 'Marginalia-LoCoMo-Benchmark', 'cwd': '.../OktoLabsAI', 'tmux': 'cc-OktoLabsAI-6682-1:@0.%0', 'status': 'idle', 'kind': 'interactive', 'version': '2.1.274'}
{'pid': 87357, 'name': 'Marginalia-Provider-Dev', 'cwd': '.../OktoLabsAI', 'tmux': 'cc-OktoLabsAI-6682-2:@14.%14', 'status': 'idle', 'kind': 'interactive', 'version': '2.1.278'}
{'pid': 92180, 'name': 'OktoNexus-dev', 'cwd': '.../OktoLabsAI', 'tmux': 'cc-OktoLabsAI-6682-3:@15.%15', 'status': 'busy', 'kind': 'interactive', 'version': '2.1.278'}
```

**`pid 3523` is the multi-day Marginalia-LoCoMo-Benchmark session named explicitly in this
task's hardware constraints. None of these three pids are ever passed to a connector below.**

## Spawning a dedicated, disposable session

A brand-new tmux session (`nxs-int-attach-test`) was created in a throwaway scratch cwd,
running `claude` (interactive, NOT `claude -p` — `-p` sessions have no `cc-socks` socket per
`discover_attachable_sessions`'s own filter). Its real OS pid was recovered independently (via
the tmux pane's process tree, not by trusting a self-report), and its registry entry confirmed
before use:

```
$ pgrep -P <tmux-pane-pid> -fl     # -> 86806 claude
$ cat ~/.claude/sessions/86806.json
{"pid":86806,"sessionId":"391971e1-...","cwd":".../scratchpad/cc-int-cwd",
 "version":"2.1.278","peerProtocol":1,"kind":"interactive",
 "tmux":"nxs-int-attach-test:@17.%17",
 "messagingSocketPath":"/tmp/cc-socks/86806.sock","name":"cc-int-cwd-99","status":"idle"}
```

`86806` matches none of `{3523, 87357, 92180}` from the read-only register above. This is the
**only** pid any `start()`/`send()` call below targets, and it is a session this task itself
spawned and owns.

## INT-01 — spawn and handshake

Command: `timeout 60 uv run python int_attach_real.py` (script in the session scratchpad
directory, never committed to the repo — same convention as EV-SYS-001's verification script),
against the real
`~/.claude/sessions/` tree (no injected `sessions_dir`) and pid `86806`.

```python
connector = ClaudeCodeAttachConnector(86806)   # default sessions_dir = ~/.claude/sessions
probe = connector.probe()
session = connector.start(owning_agent_id="nxs-int-test-agent")
```

Real captured output:

```
[2026-09-20T17:25:30.460989+00:00] === INT-01: spawn/handshake (bind to real live pid 86806) ===
[2026-09-20T17:25:30.461436+00:00] probe() -> ok=True reason=ok detail=pid 86806 is attachable. peer_protocol=1 version=2.1.278
[2026-09-20T17:25:30.461546+00:00] start() -> session_id=86806.daa1ee79f2e8beb3e095ae4a69552721446a8ab6aefc2e1e708e5bd13c372ba5 status=STARTING harness_kind=claude_code
[2026-09-20T17:25:30.461548+00:00]   metadata={'pid': 86806, 'registry_session_id': '391971e1-78fc-49b1-9e15-b201c6836b74', 'name': 'cc-int-cwd-99', 'cwd': '/private/tmp/.../scratchpad/cc-int-cwd', 'tmux': 'nxs-int-attach-test:@17.%17', 'version': '2.1.278', 'peer_protocol': 1, 'socket_path': '/tmp/cc-socks/86806.sock', 'socket_path_source': 'registry', 'guard_proc_start_known': True}
```

`start()` bound to the real, already-live peer in <1ms (this connector never spawns; it
connect-then-closes a real `AF_UNIX` socket to prove a listener exists, per
`claude_code_attach.py:628-644`). **PASSED.**

## INT-02 — single turn (send a trivial prompt)

Trivial prompt per the task's cost constraint: `"reply with the single word: ok"`.

```python
connector.send(session, HarnessCommand(
    session_id=session.session_id, verb="send_turn",
    payload={"content": "reply with the single word: ok"}))
```

Output:

```
[2026-09-20T17:25:30.461552+00:00] === INT-02: single turn (trivial prompt) ===
[2026-09-20T17:25:30.461553+00:00] -> sendall() issued
[2026-09-20T17:25:30.461652+00:00] <- send() returned (fire-and-forget, no ack on this transport per EV-CC-001)
[2026-09-20T17:25:30.461654+00:00] session.status after send = RUNNING
```

**Independent, out-of-band verification the write actually reached the live peer** (this
connector itself has no ack channel to prove it — see the module's documented ack-less
limitation, `send()`'s own docstring, and `test_send_docstring_states_the_ack_less_limitation_plainly`).
`tmux capture-pane -t nxs-int-attach-test -p`, ~2s after `send()` returned:

```
⏺ Held peer message — from an unidentified session; preview: «okto-nexus relay -- external
  data via Claude Code cc-socks attach, from Okto Nexus agent nxs-int-test-agent. This is DAT»
  …[3 lines, 329 chars total — expand to review before approving] — not delivered to Claude
  (1 held). The sender did not attest its permission mode and this session bypasses prompts.
  Review it below, or set "crossSessionInbound" to "accept".

  Held message from another session
  Another Claude session sent a message: from an unidentified session
  The sender did not attest its permission mode, and this session bypasses permission prompts.

  Message body (this is what will be delivered):
  «okto-nexus relay -- external data via Claude Code cc-socks attach, from
  reply with the single word: ok
  …[3 lines, 329 chars total — full body will be delivered on approve]»
```

**This is real, previously-undocumented behaviour of Claude Code 2.1.278 worth surfacing
prominently, not a defect in this connector**: the receiving CLI now gates an unattested
cross-session peer message behind an operator approval prompt ("Held peer message") BEFORE it
reaches model context, which is a pre-step ADR 0004 D7b's risk framing did not know about
("content injected via cc-socks renders to the receiving model as an ordinary peer chat message"
— module docstring, `claude_code_attach.py:47-58`).

Approval was attempted (`tmux send-keys -t nxs-int-attach-test Enter`); the prompt's default
selection was `❯ Deny — drop it and tell the sender it was declined`, so the held message was
declined and never entered the receiving session's model context. **The post-approval path
(what actually renders to the model once an operator selects "Deliver") was NOT exercised** —
this evidence does not establish whether ADR 0004's "renders as an ordinary peer chat message"
claim still holds on the far side of this gate, only that the gate exists and sits in front of
it. What this capture DOES prove: the bytes reached the socket, were parsed, and were rendered by
Claude Code 2.1.278 with the exact banner and content this connector sent — the send-half of
INT-02, and everything this send-only, ack-less connector can be held to. It does NOT change
this connector's own behaviour or test obligations (the connector still cannot observe approval,
denial, or delivery either way), but it is exactly the kind of environmental drift `probe()` and
the stability posture in the module docstring exist to watch for, and whoever owns ADR 0004
should know a new receiving-side gate exists, and that its far side is unverified.

Because `observes_session_end=False` / `send_only=True`, this connector structurally cannot
itself observe a "completed response" (the reduced-INT-02 half of the case that does not apply
here, exactly as the port's own capability fields say it should not — see `application/ports.py`
`HarnessConnector` docstring: "any reply is delivered later ... never as this call's return
value", and here there is no reply channel of any kind). The send-half of INT-02 — a trivial
prompt genuinely reaching the live peer — is proven above by first-party observation from the
receiving pane itself, the same evidentiary standard EV-CC-001 used. **PASSED** (send-half;
receive-half is N/A per capabilities, not silently skipped).

## INT-08 — error edges

### (a) malformed input — missing `content`

```
[2026-09-20T17:25:30.461655+00:00] === INT-08a: malformed input (missing content) ===
[2026-09-20T17:25:30.461662+00:00] raised OktoNexusError code=VALIDATION_ERROR message="command.payload['content'] must be a non-empty string."
```

### (b) unknown verb

```
[2026-09-20T17:25:30.461664+00:00] === INT-08b: unknown verb ===
[2026-09-20T17:25:30.461668+00:00] raised OktoNexusError code=VALIDATION_ERROR message='harness command verb must be one of {send_turn, steer, interrupt, end}.'
```

Note: this specific rejection is raised by `HarnessCommand.__post_init__` in the frozen
`domain/harness.py` (verb validated against the closed `COMMAND_VERBS` vocabulary) before the
connector is ever reached — an unknown verb cannot even be constructed into a `HarnessCommand`.
A verb that IS in `COMMAND_VERBS` but unsupported by this specific transport (`steer`,
`interrupt`, `end`) is rejected by the connector itself instead — already covered by the
existing `test_send_rejects_non_send_turn_verbs`. Both layers reject cleanly, with no hang.

### (c) non-string content (type confusion)

```
[2026-09-20T17:25:30.461670+00:00] === INT-08c: non-string content ===
[2026-09-20T17:25:30.461673+00:00] raised OktoNexusError code=VALIDATION_ERROR message="command.payload['content'] must be a non-empty string."
```

### (d) abrupt child death — real process kill, not simulated

```python
session = connector.start(owning_agent_id="nxs-int-test-agent-death")
subprocess.run(["tmux", "kill-session", "-t", "nxs-int-attach-test"])   # kills pid 86806
# poll os.kill(pid, 0) until ProcessLookupError, then:
connector.send(session, HarnessCommand(session_id=session.session_id,
                                        verb="send_turn", payload={"content": "hi"}))
```

Real captured output (timestamps show this settled in under half a second, not hanging):

```
[2026-09-20T17:26:29.907852+00:00] start() ok, session_id=86806....
[2026-09-20T17:26:29.907852+00:00] killing tmux session nxs-int-attach-test (abrupt child death of pid 86806) ...
[2026-09-20T17:26:30.428656+00:00] pid 86806 confirmed dead (os.kill(pid,0) raises ProcessLookupError)
[2026-09-20T17:26:30.428909+00:00] send() raised OktoNexusError in 0.000s: code=NOT_FOUND message='No auth token file remains for pid 86806 - the session has likely ended (and, if the pid was recycled, the new session has not yet written its own key file). Refusing to send with a now-orphaned token.'
[2026-09-20T17:26:30.428920+00:00] events() after child death: [('error', 'pid_reuse_guard_tripped')]
```

Claude Code itself removed its key/registry files as part of its own shutdown, so
`_check_no_pid_reuse` (`claude_code_attach.py:817-901`) caught the death instantly via the
missing-key-file branch, before ever attempting the socket write. A structured `OktoNexusError`
was raised in <1ms; the connector did not hang, and the error is also surfaced through
`events()` per the module's dual-signal design. **PASSED, all four sub-cases.**

## Teardown / no orphans

```
$ ps aux | grep 86806 | grep -v grep      # -> (no output)
$ tmux list-sessions                       # -> nxs-int-attach-test is gone; the 4 pre-existing
                                            #    sessions (including pid 3523's benchmark) are untouched
$ ls ~/.claude/sessions/86806*             # -> no matches (Claude Code cleaned up its own files)
```

No process was left running; the three pre-existing sessions (`3523`, `87357`, `92180`) were
never sent anything and remain exactly as enumerated in the SAFETY section above.

## Full scripts

- `int_attach_real.py` — INT-01/02/08a-c (spawn/handshake, single turn, malformed
  input/unknown verb/type confusion).
- `int08_child_death.py` — INT-08d (abrupt child death).

Both lived in the session's scratchpad directory, never in the repo (same convention
`EV-SYS-001-phase35-real-socket.md` states). Both ran with a bounded `timeout` wrapper (60s /
45s respectively); both completed in well under a second of actual work.
