# Canonical publication of captured conversation results

Execution parent `41c3322`, branch `feature/v0.2.0`, 2026-09-23. Partial P08
implementation; P09 native approval/input bridging is not implemented by this
unit, and no phase/final gate is declared passed.

Migration 041 links results to canonical messages and approvals. Existing
pre-migration pending results become `REVIEW_REQUIRED`; upgrading does not send
historical output to other agents. New correlated inbox results are considered
for publication in bounded batches by the serve dispatcher after projection.
Administrative command and uncorrelated results remain private.

`RuntimeResultService` derives identity, workspace, parent and direct recipient
from the correlated durable inbox operation. It revalidates agent activity,
original actor credential binding, endpoint/profile revisions and the approved
conversation response policy. Native text cannot select another author or
audience. `MessageService.create_message` remains the canonical path for
permissions, communication scope, rate limits, governance, guardrails, inbox
fan-out and approvals. The internal result reference is not an MCP/REST input.
Strict trust mode accepts this verified captured principal without injecting
an operator key or fabricating a session secret.

Message, delivery, event and publication reference commit in one UoW. A crash
before commit leaves the result pending; retry produces one logical message.
Already published results return the same message. Denials leave captured
output intact and publication `BLOCKED`. Approval interception and its result
link commit together. The canonical operator decision revalidates the binding
before publication; rejected approvals do not publish the captured output.
The approval ID remains linked after successful publication.

Replies are directed to the original message author, not broadcast. They are
non-executing notifications in this unit; P10 still must implement explicitly
authorized continuation with persistent causal budgets. Likewise, approval
rejection notices remain inbox messages without launching a new native turn.
The new test reproduced that prior bug (2 outbox rows instead of 1) before
adding the internal non-executing notification marker to the canonical path.
No handoff is completed by publication. Publication does not call an embedding
provider on the dispatcher thread.

Current output limit: publication carries at most a 60,000-byte text preview
with an explicit truncation marker. The captured result remains private and
durable. Authorized artifact storage/publication is still pending; this preview
is not a substitute for that P08 requirement. Explicit broadcast notification
configuration, retrospective review/retry administration and database retention
also remain pending.

Validation:

- Initial publication/permissions/transaction rollback: 3 passed in 11.81s.
- Added approval/source substitution checks: 6 passed in 15.43s.
- Rejection-notification regression: 1 FAILED, 5 deselected in 5.11s before fix;
  corrected selection: 6 passed in 17.73s.
- Added actual guardrail and approval revocation checks: 8 passed in 25.91s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_result_publication.py tests/test_runtime_result_correlation.py
  tests/test_runtime_restart.py tests/test_runtime_commands.py tests/test_hitl.py
  tests/test_governance.py tests/test_guardrails.py tests/test_import_boundary.py
  --tb=short --maxfail=4`: 120 passed in 105.18s (before final notification fix).
- Final expanded Windows selection:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_result_publication.py tests/test_hitl.py tests/test_governance.py
  tests/test_guardrails.py tests/test_runtime_shutdown.py
  tests/test_runtime_result_correlation.py tests/test_import_boundary.py
  --tb=short --maxfail=4`: 110 passed in 69.85s; one existing Starlette/httpx
  deprecation warning.
- Linux production fixture composition:
  `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus --
  /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q
  tests/test_runtime_result_publication.py tests/test_runtime_result_correlation.py
  --tb=short --maxfail=3`: 13 passed in 52.73s.
- Subsequent feature-disable/strict-principal case:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_result_publication.py::test_disabled_feature_preserves_pending_result_and_strict_mode_uses_captured_principal
  --tb=short`: 1 passed in 5.00s.
- Ruff changed production modules: PASS. Native provider campaigns NOT_RUN for
  this unit; previous native counts do not qualify publication or native HITL.
