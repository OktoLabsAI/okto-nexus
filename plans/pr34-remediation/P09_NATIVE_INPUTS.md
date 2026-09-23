# P09 — explicit native input responses, contract 1

Parent `bd0b5f2`, 2026-09-23. Additive migration 049; no personal store migrated.
Surface revision remains 38 (existing MCP schemas unchanged); REST decision body
adds optional `response`, rejected for actions that do not support input data.

## Implementation and operator usage

`domain/native_inputs.py` validates bounded, non-secret blocking Codex questions
and correlated MCP form elicitation with flat string/boolean/number/integer fields.
No schema resolver, network or process call occurs during validation. URL mode,
unmatched turn, secret questions, nonblocking requests, external schema references
and unsupported schema constructs are rejected without following URLs or inventing
answers. Limits: 16 questions/properties, 16 options/answers, 4096 characters per
answer, 16KiB serialized response. Supported constraints are enforced; defaults
do not become implicit human selections.

Native requests use the existing journal/HITL path. `ApprovalService` registers
transactional decision validators and operator-only detail providers per action.
`RuntimeNativeApprovalService.validate_decision` writes the private response in
the SAME SQLite transaction as the canonical human decision. Failed validation or
transaction rollback leaves both unchanged. Identical decision/answer retries are
idempotent; a different answer conflicts. Existing binary approvals remain binary.

POST `/api/v1/approvals/{approval_id}/decision`, authenticated as operator:

```json
{"decision":"approve","response":{"answers":{"question-id":{"answers":["Selected label"]}}}}
```

For supported form elicitation:

```json
{"decision":"approve","response":{"content":{"color":"blue","count":2,"enabled":true}}}
```

Reject uses `{"decision":"reject"}` without a response. Native question rejection
returns an empty answers mapping (the protocol has no binary decision field);
form rejection returns action decline. Expiry/revocation cannot send previously
approved data: the prewrite authority check downgrades to the negative response.
The connector revalidates against its ORIGINAL request before writing; a redacted
journal projection cannot alter native options or authorize a mismatched answer.
Writes remain SENT_UNCONFIRMED; ambiguous writes are not replayed.

Operator-only GET detail now includes `decision_detail` with the durable native
state, reason, deadline and response. Queue summaries/events do not expose answers.
UI rendering and administrative MCP parity remain P11 work.

## Evidence

Installed Codex generated schemas in a temporary directory via `app-server
generate-json-schema --out <temporary-directory>`. Hashes and required properties
are recorded in `evidence/p09-native-input-schema.json`. This was local schema
inspection only, not a model call. Native input/elicitation campaign **NOT_RUN**;
the preceding real binary-approval campaigns are not reused as input evidence.

- Behavioral RED: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_native_inputs.py -x`:
  **1 FAIL, 9.65s**, a valid question never reached HITL. Initial correction:
  **1 PASS, 5.58s**.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_native_inputs.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_approvals.py tests/test_hitl.py tests/test_runtime_profile_requirements.py`:
  **60 PASS, 150.92s**, one existing Starlette deprecation warning.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_native_inputs.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_approvals.py tests/test_runtime_profile_requirements.py`:
  **40 PASS, 151.50s**.
- Later operator detail check: Windows targeted `-k explicit_operator -x`:
  **1 PASS, 10 deselected, 6.05s**.
- Expanded Windows `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_native_inputs.py`:
  **16 PASS, 65.15s**. Includes allow/reject, invalid/missing answers, caller
  denial, private detail, response-changing retry, transactional cut, expiry,
  secret/nonblocking input rejection, URL/remote-schema/no-turn rejection.
- Ruff changed files: **PASS**.

Claude AskUserQuestion support remains a separate next unit (official user-input
contract inspected, not yet implemented here). Pi input capabilities are not
inferred; dedicated attach remains send-only. Remaining P09 gates, P10–P12 and
final feature-enabled acceptance are not complete.

Expanded Linux command: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_native_inputs.py`: **16 PASS, 68.08s**, including the late private-detail and transactional-cut additions.
