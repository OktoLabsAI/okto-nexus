# P09 — Claude stream permission bridge

Parent `1338d86`, 2026-09-23; migration 048 unchanged. No personal database touched.
P09 remains IN_PROGRESS. No final acceptance claim.

## Protocol and implementation

Official protocol source inspected:
[Anthropic SDK query control handler](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/query.py)
and [CLI transport](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/transport/subprocess_cli.py).
The handler identifies permission requests by request_id and can_use_tool, returns
allow with original updatedInput or deny with a message, and honors cancellation.
These sources motivated the wire implementation; the installed binary test below
provides separate execution evidence. No SDK dependency was added.

`ClaudeCodeStreamConnector` enables `--permission-prompt-tool stdio` only for the
production default command when canonical HITL is enabled. The adapter admits
one-shot Write/Edit/Bash permission requests, hashes their original input, and
publishes them through the same durable journal/ApprovalService/owner worker as
Codex. Policy changes, ExitPlanMode and AskUserQuestion are not silently treated
as binary tool permission. Unsupported requests receive a protocol error.

Claude does not supply Codex thread/turn IDs in this permission contract. The
existing exact operation/attempt correlation remains authoritative. A separate,
explicitly local generation advances on observed system:init; result/cancel
invalidates pending native replies. No invented native turn ID is persisted:
empty native-ID columns on the request record mean absent, matched against NULL
on the source operation. Native request ID is unique for the entire connection.
Limits: 16KiB per request, 32 pending, 256 lifetime records. Late/reused IDs cannot
authorize a new turn. Original in-memory input is returned on allow; journal
redaction is never used to modify native tool arguments.

Catalog advertises this restricted method/tool list and HITL dependency. Attach
is unchanged. No sandbox bypass, permission-mode override, updatedPermissions,
operator key, generic approval or automatic retry was introduced.

## Evidence

- RED on parent: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_claude_approvals.py -x`:
  **1 FAIL, 10.66s**, valid permission never reached HITL.
- Initial corrected fixture run: same command **2 PASS, 8.16s**.
- Installed version: `rtk proxy C:/Users/jpamb/.local/bin/claude.exe --version`:
  **2.1.280**.
- REAL isolated command:

```powershell
rtk proxy python -c 'import os,subprocess; env=os.environ.copy(); env.update(OKTO_NEXUS_NATIVE_CAMPAIGN="claude_code", OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/.local/bin/claude.exe", OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.claude/.credentials.json", OKTO_NEXUS_PI_LIVE="0", OKTO_NEXUS_CODEX_LIVE="0", OKTO_NEXUS_CLAUDE_LIVE="0"); raise SystemExit(subprocess.call([".venv/Scripts/python.exe","-m","pytest","-q","tests/test_runtime_native_campaign.py","-k","approval_denial"],env=env))'
```

First run failed before handoff creation due to a test-string concatenation error:
**1 FAIL, 1 SKIP, 5 deselected, 5.54s**. Fixed test expression, fresh isolated run:
**1 PASS, 1 SKIP, 5 deselected, 19.79s**. Codex parameter skipped because this
invocation explicitly selected Claude. Canonical handoff/grant triggered actual
Write permission; operator denial returned, no file appeared, turn settled and
owned process stopped. Only the selected login was copied into a temporary home
and removed by fixture teardown. No ambient hooks/settings/MCP/sessions reused.

Real allow/Edit/Bash remain NOT_RUN; binary allow and wire constraints have fixture
coverage. Input/elicitation is still pending; this unit does not answer questions.
Further regression results are recorded in IMPLEMENTATION_STATUS.md/backlog.

Expanded Windows: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_claude_approvals.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_admission.py tests/test_harness_claude_code_connector.py`: **50 PASS, 7 SKIP, 132.47s**. Linux: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_claude_approvals.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_admission.py tests/test_harness_claude_code_connector.py`: **50 PASS, 7 SKIP, 138.57s**. Seven legacy real-Claude cases require a separate explicit opt-in and remain NOT_RUN here. Added scenarios cover native cancellation, terminal before decision, consumed ID reuse across turns, and unsupported policy/input tools. Ruff changed files PASS.
