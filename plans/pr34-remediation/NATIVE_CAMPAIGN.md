# Native connector campaign — 2026-09-22

User authorized the local Codex installation and subsequently local Claude.
Pi native remains **NOT_RUN** by instruction. All commits/pushes remain on
`feature/v0.2.0`. Parent SHA for this execution: `93d5fab`, with the P08 unit in
the working tree (committed together with this evidence).

## Actual two-turn execution

| Adapter | CLI version | Observed model/provider | Result |
|---|---|---|---|
| Codex app-server | 0.155.1 | gpt-6-astra / openai | PASS: two turns, one native thread, 2 captured results, process reaped |
| Claude stream-json | 2.1.277 | claude-opus-5 / claude-opus-5[1m] | PASS: two turns, one native session, 2 captured results, process reaped |
| Pi RPC | Not executed | — | NOT_RUN, user instruction |
| Claude attach cc-socks | No dedicated session executed | — | NOT_RUN; do not substitute a personal interactive session |

These are narrowly scoped PASS results. Steering, interrupt/settle, native
approval requests, reconnect, shared-process multiplexing, adversarial load and
the full final matrix are **not certified** by these two tests.

The test starts the real production HTTP/MCP app and serve dispatcher with no
connector factory replacement. An explicitly enabled endpoint points to the
absolute local executable. Authenticated `message_create` creates canonical inbox
deliveries and transactional outbox intents. Native events flow through the
production journal/projector. The test verifies preserved canonical agent role
and metadata, two durable results, stable native session/thread, no operator key
in the child environment and observed process exit after REST close.

Each run used a temporary project, Nexus store and native configuration directory.
Only the installed CLI's login file was copied temporarily; no personal settings,
hooks, MCP server configuration or existing sessions were copied. Both temporary
auth copies were verified removed. Codex used read-only/on-request. Claude used
its native default permissions; **no claim of an OS sandbox is made for Claude**.
Neither runtime received bypass flags or the Nexus operator key.

The observed native payloads, not guessed product defaults, supplied the model
names above. CLI versions were independently probed with `--version` under a
minimal OS environment. The committed JSON contains only selected non-secret
observations; temporary raw stores/transcripts and authentication files are not
committed.

## Exact commands

Codex, PowerShell:

```powershell
$env:OKTO_NEXUS_NATIVE_CAMPAIGN='codex'
$env:OKTO_NEXUS_TEST_EXECUTABLE='C:\Users\jpamb\AppData\Roaming\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'
$env:OKTO_NEXUS_TEST_AUTH_SOURCE='C:\Users\jpamb\.codex\auth.json'
.venv/Scripts/python.exe -m pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short
```

**1 passed, 1 deselected**, 10.71s: `evidence/p07-native-codex.log`.

Claude, in a separate PowerShell invocation:

```powershell
$env:OKTO_NEXUS_NATIVE_CAMPAIGN='claude_code'
$env:OKTO_NEXUS_TEST_EXECUTABLE='C:\Users\jpamb\.local\bin\claude.exe'
$env:OKTO_NEXUS_TEST_AUTH_SOURCE='C:\Users\jpamb\.claude\.credentials.json'
.venv/Scripts/python.exe -m pytest tests/test_runtime_native_campaign.py -q -k claude_code --tb=short
```

**1 passed, 1 deselected**, 8.18s: `evidence/p07-native-claude.log`.
Structured observations: `evidence/p07-native-observations.json`.

With no opt-in, `pytest tests/test_runtime_native_campaign.py -q` skips both tests
without reading authentication files or starting native processes. After the
runs, auth cleanup was moved to a pytest fixture so bootstrap failures also remove
the temporary copy; no native rerun was needed for that cleanup-only adjustment.

Profile validation also now rejects explicit Codex sandbox/approval fields on Pi
or Claude profiles, including previously stored profiles at construction time:
silently ignoring such options would falsely claim controls the adapter does not
implement. Validation check: **2 passed, 2 skipped, 16 deselected**, using
`pytest tests/test_runtime_endpoints.py tests/test_runtime_native_campaign.py -q -k 'unimplemented_sandbox or native_two'`;
`evidence/p07-profile-capabilities.log`. The first test assertion expected HTTP 400;
the existing API correctly uses 422 for VALIDATION_ERROR and the assertion was
corrected. This was a test expectation error, not a behavior reproduction.

## Subsequent Codex active-close campaign

Parent `866753a` plus the active-close working tree: explicit same Codex paths,
fresh isolated configuration and canonical inbox delivery. Command:
`pytest tests/test_runtime_native_campaign.py -q -k active_close --tb=short`.
**1 passed, 2 deselected, 5.39s**. Codex 0.155.1 / observed gpt-6-astra.
Matching native interrupted terminal was journaled before observed process stop;
temporary auth copy removed. See P07_CODEX_ACTIVE_CLOSE.md and
`evidence/p07-native-codex-active-close-observations.json` for scope and limits.
The test module now contains three opt-in cases; default execution skips all
three. Prior two-turn counts above are historical results, not current collection
counts or claims of coverage for subsequent changes.

After native request ordering/pending-start fencing (parent 1780f15 plus working
tree), the same isolated Codex configuration ran
`pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short`:
**2 passed, 1 deselected in 18.04s**. This re-executes both two-turn canonical
delivery and active-close interruption, including the final atomic-close lock
refinement. Evidence: `evidence/p07-native-codex-request-race-gate.log` and
P07_CODEX_REQUEST_ORDERING.md. Temporary authentication copies checked absent.

After bounded native stream v2 (parent 2b6b3a9 plus working tree), fresh isolated
campaigns reran the authorized paths: Codex **2 passed, 1 deselected, 15.51s**;
Claude stream **1 passed, 2 deselected, 10.55s**. Commands retain the same explicit
paths/configuration above and select `-k codex` / `-k claude_code` respectively.
See P07_EVENT_BUFFERS.md and `evidence/p07-native-buffer-observations.json`.
These prove normal enabled operation with bounded history/fanout, not real native
pressure/fault campaigns. All login copies removed; Pi and attach native NOT_RUN.

2026-09-23, bac6f71 plus early-event limits working tree: same explicit isolated
Codex configuration, `pytest tests/test_runtime_native_campaign.py -q -k codex
--tb=short`: 2 PASS, 1 deselected in 14.67s. See P07_CODEX_EARLY_EVENTS.md and
evidence/p07-codex-early-events-native.log. Two-turn and active-close paths only;
no new Claude/Pi/attach native execution in this unit.

2026-09-23, 7e3e774 plus Claude admission working tree: same explicit isolated
Claude configuration, `pytest tests/test_runtime_native_campaign.py -q -k
claude_code --tb=short`: 1 PASS, 2 deselected in 9.36s. See
P07_CLAUDE_ADMISSION.md and evidence/p07-claude-admission-native.log. Canonical
two-turn path only; native pressure/steering/approval campaign still NOT_RUN.

2026-09-23, 30f340c plus attempt correlation working tree: REAL isolated Codex
2 PASS / 1 deselected / 22.13s and Claude stream 1 PASS / 2 deselected / 11.58s.
Two-turn tests now require matching durable operation/attempt/terminal linkage.
See P08_RESULT_CORRELATION.md and evidence/p08-result-correlation-{codex,claude}.log.
No Pi/attach native execution; no native approval/load campaign claim.

2026-09-23, 924c3ef plus consumption/materialization worktree: Codex 2 PASS,
1 deselected, 20.71s; Claude stream 1 PASS, 2 deselected, 12.92s. Same explicit
isolated configuration and commands. Two-turn cases additionally assert nonempty
untruncated derived text and canonical consumption of the two push deliveries.
See P08_CONSUMPTION_MATERIALIZATION.md and its exact evidence logs. No Pi/attach
native execution and no change to broader native NOT_RUN declarations.

2026-09-23, e482655 plus coordinated shutdown worktree: fresh REAL isolated Codex
2 PASS / 1 deselected / 15.46s; Claude stream 1 PASS / 2 deselected / 8.21s.
Same explicit configuration and native cases; no new native shutdown stress claim.
See P07_COORDINATED_SHUTDOWN.md and evidence/p07-shutdown-native-{codex,claude}.log.
