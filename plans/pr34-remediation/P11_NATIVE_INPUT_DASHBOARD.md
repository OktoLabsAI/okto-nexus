# P11 — explicit native input in the operator dashboard

Parent `43e06cc` (feature/v0.2.0),2026-09-23. Package0.2.0, schema053,
surface41 and identity resource8 unchanged. Frontend builds used temporary
directories; the user's three generated static files remain untouched.

## Finding and implementation

The backend's existing response contract accepted typed native input, but
ApprovalsView/api.decideApproval sent only approve/reject/justification. An
operator could not supply answers through the shipped dashboard. The actual
browser reproduced the missing question control while a real protocol fixture
waited behind the production HTTP/MCP/dispatcher/journal/HITL composition.

`frontend/src/components/NativeApprovalInput.tsx` now renders the supported
Codex question, primitive form elicitation and Claude AskUserQuestion contracts.
No default selection or automatic submission. Choices remain arrays when needed,
form numbers/booleans retain types, optional absent fields stay absent, and an
explicit empty-string choice is available when allowed. Answer size is bounded;
the canonical backend remains authoritative for schema, policy, native turn,
expiry and idempotency validation.

`frontend/src/api.ts` forwards optional response and types decision_detail.
`ApprovalsView.tsx` requires reviewing native requests, separates permission
approval from sending input, displays delivery state/reason/response, and removes
answer controls for expired/non-pending native records. It labels native requests
correctly instead of describing them as broadcast. Detail fetch generations and
approval IDs prevent stale requests from replacing another row's detail; current
approval refreshes reload detail. Agent credentials still cannot decide; these
operator UI calls use the existing REST/ApprovalService. No autonomous MCP HITL
decision surface was added.

## Reproducible browser campaign

Prerequisites installed for this execution:
`rtk proxy uv pip install --python .venv/Scripts/python.exe playwright` installed
playwright1.63.0, pyee13.0.1 and greenlet3.5.6 in the test venv. Node/Vite dependencies
and installed Edge were already available. Observed Edge153.0.4234.48. Test source
`tests/test_runtime_input_dashboard.py` is explicitly opt-in via
OKTO_NEXUS_UI_CAMPAIGN=1; unconfigured environments skip and remain NOT_RUN.

The browser launches a fresh temporary profile/context with chromium_sandbox=True.
Only disposable fixture operator authentication is placed in that browser session;
no personal browser profile, provider login or native account is used. Page
network access is restricted to the fixture loopback server. Only static assets
are fulfilled from a temporary build; all API calls use the real authenticated
production application. Both native connector transports run actual Python
protocol peers, never a model. Context/browser and owned peers close on teardown.

The fixture runs `node node_modules/vite/bin/vite.js build --outDir <pytest-temp>`
from frontend; this preserves the repository's generated assets.

Exact commands/results:

- `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ["OKTO_NEXUS_UI_CAMPAIGN"]="1"; raise SystemExit(pytest.main(["-q","tests/test_runtime_input_dashboard.py","-x"]))'`:
  first setup ERROR59.80s from the onboarding overlay; corrected fixture to close
  onboarding and dismiss metrics consent without enabling metrics. Then
  **behavioral RED**,1 failed24.98s: the actual native question had no answer field.
  After implementation, **1 PASS**,19.50s.
- `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ["OKTO_NEXUS_UI_CAMPAIGN"]="1"; raise SystemExit(pytest.main(["-q","tests/test_runtime_input_dashboard.py"]))'`:
  **4 PASS**,33.54s: explicit Codex answer/no default action, typed form,
  Claude multi-choice and rejection without invented answer.
- `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ["OKTO_NEXUS_UI_CAMPAIGN"]="1"; raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_input_dashboard.py"]))'`:
  expanded **5 PASS**,41.38s. Final expanded run **6 PASS**,53.69s, including
  permission approval, expiry/no answer control, explicit empty text and latest UI.
- `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ["OKTO_NEXUS_UI_CAMPAIGN"]="1"; raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_input_dashboard.py","-k","form_preserves"]))'`:
  intermediate explicit-empty-text addition **1 PASS /4 deselected**,16.58s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_native_inputs.py tests/test_runtime_claude_approvals.py tests/test_hitl.py`:
  **48 PASS**,109.21s; one existing Starlette/httpx deprecation warning.
- `rtk proxy node frontend/node_modules/typescript/bin/tsc --project frontend/tsconfig.json --noEmit`:
  **PASS**, including final sources. `rtk proxy ruff check tests/test_runtime_input_dashboard.py`:
  **PASS**. `rtk git diff --check`: **PASS**.

Visual inspection of the actual final form: [fixture screenshot](evidence/p11-native-input-form.png).
Labels, explicit values, decision/delivery distinction and original request were
checked at1440x1000. It contains disposable fixture data only.

## Remaining gates

This supplies partial T-API-08/P11-T03 dashboard evidence, not its full gate:
unknown/ambiguous operations and detached-process diagnostic UI remain pending.
Windows browser campaign PASS; Linux browser NOT_RUN. Real Codex/Claude models
NOT_RUN for this unit; prior native results remain separate. Pi/dedicated Claude
attach native NOT_RUN. Capability probes, outbox reconciliation, remaining admin
parity, full guide/ADR, P12 campaign and final build/install remain pending.
Final gate NOT PASSED.
