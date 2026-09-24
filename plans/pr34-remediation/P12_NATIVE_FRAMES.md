# P12 — observed native frames at 752cd72

2026-09-24. Source `752cd72cc28c1b623f52b796fb139d375357f89b`,
`feature/v0.2.0`, Windows. Implementation/tests remained unchanged throughout.
Final gate NOT PASSED; these are scoped native protocol results.

## Commands and observed results

```text
rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/native_frame_campaign.py --adapter codex --executable C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe --auth-source C:/Users/jpamb/.codex/auth.json --output plans/pr34-remediation/evidence/p12-frames-752cd72-codex.json
rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/native_frame_campaign.py --adapter claude_code --executable C:/Users/jpamb/.local/bin/claude.exe --auth-source C:/Users/jpamb/.claude/.credentials.json --output plans/pr34-remediation/evidence/p12-frames-752cd72-claude.json
```

| Adapter | Native version | Executed tests | Frames | Result |
| --- | --- | --- | --- | --- |
| Codex app-server | 0.156.1 | 7 passed, 8 deselected, 132.09s | 1639 | PASS |
| Claude stream-json | 2.1.281 | 6 passed, 9 deselected, 66.07s | 239 | PASS |

Both tested canonical inbox two-turn delivery, managed work preserving separate
handoff verification, operator denial of native approval, steering and interrupt.
Codex additionally tested active close and production multiplexing with sibling
survival; Claude additionally tested native question/operator input. Deselected
cases are other-adapter cases and separate qualification paths, not passes.

Codex outbound: initialize7, session_start8, turn_start10, session_detach8,
interrupt2, control_reply1, steer1. Claude outbound: turn_start8, control_reply2,
interrupt2. Claude steering uses its implemented interrupt/next-turn contract;
it does not become a fabricated native steer command. Neither campaign observed
outbound status queries or unclassified outbound methods; neither overflowed
the recorder. Protocol reads and writes were observed from startup to cleanup.
Returning from a write is not recorded as acceptance or completion.

The Codex protocol reported model `gpt-6-astra`, provider `openai`. The Claude
recorder did not observe a recognized model field; no model is inferred from
the binary version or login. Reports retain labels/opaque aliases, not raw
payloads, prompts, credential values or native IDs. Recorder content hash,
source SHA, per-test phases and compatibility reports are in the JSON files.

## Isolation and limits

Each test used a separate temporary project, Nexus store and native config,
copying only its explicitly approved local login file. Ambient inheritance was
disabled; sandbox/approval controls were preserved and the Nexus operator key
was not passed to the child. Tests asserted owned-process cleanup. After both
campaigns, a filename-only check found zero remaining native-config/auth.json
or native-config/.credentials.json files in these roots:

- C:/Users/jpamb/AppData/Local/Temp/okto-frame-codex-xpmnb133
- C:/Users/jpamb/AppData/Local/Temp/okto-frame-claude_code-nhl433aw

The two campaigns partially overlapped. Durations are observations, not a
comparative performance benchmark. The test driver reads Nexus operation state;
this is distinct from querying native harness status.

T-E2E-03 is PASS for these approved Codex/Claude versions/configurations. Pi native
and dedicated Claude attach remain NOT_RUN under the user's approved scope;
T-E2E-01 (three simultaneous native harnesses) and T-E2E-02 are not promoted.
Full matrix, crash/load sampling, comparable performance, rollout qualification,
final regression and final build/install0.2.0 remain separate dependencies.
