# EV-SYS-010 — SYS-10: hub stop terminates every child, leaving no orphans

Two-stage: explicit `harness_close` on every remaining live session, then `SIGTERM` to the whole
`serve` process GROUP (it was started with `start_new_session=True`, the same posture
`tests/conftest.py`'s `real_server` fixture uses for its own teardown).

`sys10_shutdown.py` is scratchpad-only (never committed, same convention as the other SYS
evidence files) — its real captured output is inlined below.

```
$ timeout 60 uv run python sys10_shutdown.py
descendant pids before close/shutdown: [61737, 61790, 61738, 61739, 61942, 62024, 62026, 62028,
  62044, 62130, 62166, 62168, 62165, 62212, 62248]
```

(pi's descendants are already absent here — SYS-08 killed that one earlier in this same run.
The `claude -p` process additionally spawned ITS OWN configured MCP servers as grandchildren
[linkedin/nanobanana/pi-delegate/reddit/waha/portainer/codegraph] — this session inherited the
operator's normal Claude Code config; they are genuine descendants of the harness child and the
orphan check below covers them too, not just the two harness binaries themselves.)

```
close codex: status=200 final_status=ENDED
close cc_stream: status=200 final_status=ENDED
close cc_attach: status=200 final_status=RUNNING

descendant pids after explicit harness_close calls: [61790, 61942, 62024, 62026, 62028, 62044,
  62130, 62166, 62168, 62165, 62212, 62248]
```

Two disclosed observations from the explicit-close stage (neither breaks SYS-10's own
requirement, checked below):

1. **codex's teardown fully reaped its child** (`61737`/`61738`/`61739` all gone) within 1s of
   `harness_close` returning. **claude_code/stream's did not** — `61790` (shim) and `61942` (real
   `claude` binary) were still alive 1s after `harness_close` returned `200`/`ENDED`. This may
   simply be that the 1s check window was shorter than the connector's own
   `close_timeout_s=10s` bound (`HarnessSupervisor`'s `_best_effort_teardown` is bounded, not
   instant) — not asserted as a defect, disclosed as observed.
2. **`cc_attach`'s close returned `final_status: RUNNING`, not a terminal status.** This is
   correct, not a bug: `capabilities.observes_session_end=False` for D7b (cc-socks), and
   `_finish_reap` explicitly skips writing a terminal status for a non-observing connector — per
   `domain/harness.py`'s own docstring, such a session "is abandoned by the peer, not
   transitioned." `harness_close` still stopped TRACKING it (removed from the live registry), it
   just never fabricates an `ENDED` it has no way to know is true.

```
SIGTERM sent to process group 59631 at wall=1789927602.121417
serve process gone: True

orphan check (any of the ORIGINAL descendant pids still alive):
[]

broad ps sweep for any surviving SYS-suite harness process (expect empty):
''
```

Two independent checks, both clean:
- **Targeted**: every one of the ORIGINAL descendant pids captured before shutdown (12 of them,
  spanning two process-tree levels) — gone.
- **Broad sweep**: `ps aux | grep` for the real binary command lines (`/opt/homebrew/bin/pi
  --provider zai`, `/opt/homebrew/bin/codex app-server`, or either PATH shim), independent of pid
  — catches a re-parented orphan under a DIFFERENT ppid too, not just the pids this script
  happened to record going in. Empty.

Full raw result: `EV-SYS-010-shutdown_result.json`.

**Verdict: SYS-10 PASS.** (The dedicated `tmux` session used for the D7b attach substrate
throughout this suite, `sys-harness-attach`, was also torn down as part of this evidence run's
own housekeeping — it held no Nexus-owned process, only the throwaway interactive `claude` peer
itself.)
