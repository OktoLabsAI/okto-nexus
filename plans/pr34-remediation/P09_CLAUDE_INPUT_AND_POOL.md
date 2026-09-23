# P09 — Claude questions and competitive pool evidence

Parent `b53866d`, 2026-09-23. Migration 049 and MCP surface revision 38 unchanged.

Claude `AskUserQuestion` now uses the same canonical explicit-response transaction
as Codex input. The adapter validates original questions, preserves them in
updatedInput, and includes only the explicit human answers. Single selections,
multiple selections and per-question free text are supported; missing answers
cannot become binary permission. Reject returns native deny, never invented data.
Existing request ID/local generation/owner/operation fencing and bounds remain.
Profile requirement: `control_request:can_use_tool/AskUserQuestion`.

Protocol reference: [Anthropic user-input contract](https://code.claude.com/docs/en/agent-sdk/user-input).
Question text keys the answer map; original questions accompany the response.
The implementation does not adopt the documentation example's automatic approval
of unrelated tools. ExitPlanMode and permission-policy updates remain unsupported.

Operator example on the existing authenticated decision endpoint:

```json
{"decision":"approve","response":{"answers":{"Choose fixture color":"blue"}}}
```

## Behavioral and native evidence

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_claude_approvals.py -k explicit_answer -x`:
  RED **1 FAIL, 8 deselected, 11.46s**, valid question never reached HITL.
  Corrected initial case **1 PASS, 8 deselected, 4.68s**.
- REAL Claude Code **2.1.280**:

```powershell
rtk proxy python -c 'import os,subprocess; env=os.environ.copy(); env.update(OKTO_NEXUS_NATIVE_CAMPAIGN="claude_code", OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/.local/bin/claude.exe", OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.claude/.credentials.json", OKTO_NEXUS_PI_LIVE="0", OKTO_NEXUS_CODEX_LIVE="0", OKTO_NEXUS_CLAUDE_LIVE="0"); raise SystemExit(subprocess.call([".venv/Scripts/python.exe","-m","pytest","-q","tests/test_runtime_native_campaign.py","-k","question_roundtrip"],env=env))'
```

**1 PASS, 7 deselected, 17.56s**. Canonical handoff + explicit execution grant
asked for one fixture question. The actual native AskUserQuestion reached HITL;
operator selected blue; native result contained blue; durable close observed
process termination. Only selected login copied into disposable config and removed
after the test. No settings/hooks/MCP/session reuse, operator key in subprocess,
file-writing tool, sandbox bypass or automatic answer. Codex native input and
form elicitation remain NOT_RUN; Pi and dedicated attach native unchanged NOT_RUN.

## Competitive pool

`test_competitive_pool_with_multiple_agents_and_endpoints_has_one_executor` uses
the real HTTP/MCP composition, two canonical agents, three approved live endpoints
(two on the same agent), and three concurrent authenticated managed claims.
The pool offer creates no executable outbox payload. Exactly one claim, one
outbox operation, one grant charge and one peer send survive. Other endpoints do
not execute. No production fix was needed: this proves the existing canonical
claim/dispatch integration under the expanded pool scenario.

Command: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_dispatch.py -k competitive_pool -x`:
**1 PASS, 16 deselected, 5.32s**. Linux pool case NOT_RUN at this checkpoint.

Remaining phase acceptance is recorded in the backlog; no final gate claim.
Next dependency after regression: P10 persistent causal roots/budgets and safe
authorized conversational relay; P11 administration/UI and P12 full campaign.

Integrated regression: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_claude_approvals.py tests/test_runtime_native_inputs.py tests/test_runtime_native_approvals.py tests/test_runtime_profile_requirements.py tests/test_hitl.py`: **69 PASS, 177.56s**, one existing Starlette warning. `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_claude_approvals.py tests/test_runtime_native_inputs.py tests/test_runtime_native_approvals.py`: **41 PASS, 161.93s**. Ruff changed files PASS.
