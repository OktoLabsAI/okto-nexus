# P09 — safe identity context and original creation authority

2026-09-23, parent `4b4b684`. This document belongs to the following implementation
commit; P09 remains IN_PROGRESS. Final gate NOT PASSED.

## Implementation and contracts

`runtime_bootstrap.delivery_context` reads the canonical Agent repository in the
same transaction that admits a conversation or managed handoff transport intent.
DeliveryEnvelope v1 gains optional `runtime_context`, with its own schema_version
1. It contains agent_id, role, normalized capability names, workspace, endpoint,
approved execution-profile ID/revision, delivery purpose and reception/completion
instructions. Existing persisted envelopes without this optional context remain
decodable. No new MCP tool or schema revision is required by this internal
additive field.

The projection is persisted inside the existing envelope and its request hash;
retries do not reconstruct a different identity snapshot. Native framing sends it
as context accompanying untrusted content. It does not elevate instructions,
grant OS permissions or become an authentication principal. Metadata, key hashes,
private communication policies, secrets/configuration and other agents' profiles
are excluded. Capability names are descriptive skills, not execution authority.

`RuntimeDeliveryPlanner.enqueue` and `RuntimeWorkService.enqueue` are the actual
production callers. Conversation explicitly carries no work authority. A managed
delivery identifies its canonical claim and explains that native turn completion
does not complete the handoff; an authenticated canonical action is required.
This unit does NOT provision subprocess tool credentials, implement a structured
completion mapper or claim native HITL support. Those remain P09 dependencies.

During review, a second behavioral defect was reproduced: changing creation
policies to deny or require approval after handoff creation could be adopted as
the initial managed dispatch authorization. Migration 046 adds
`handoff_authorization_receipts`; canonical creation atomically records the
creator's policy revision and HITL flag state only after creation is authorized.
Pending approval produces neither receipt nor executable work. Approved
re-execution passes canonical validation and creates the receipt with the handoff.

`HandoffService.validate_managed_claim` requires that receipt and unchanged
creation authority at admission, native dispatch and managed-result publication.
It does not re-charge a creation quota. Current permissions, audience, eligibility,
guardrails, grant and claim generation continue to be checked separately.

## Migration and operation

046 is additive; no existing migrations or user stores were changed. Historical
handoffs have no invented receipt. They retain their canonical unmanaged
claim/complete behavior, but managed dispatch is denied until a fresh authorized
handoff is created or an explicit review/adoption workflow is implemented.
Changing creation policies or the HITL flag also requires fresh authorization;
do not insert a receipt manually to bypass review. Safe adoption/reconciliation
remains an administrative P11 dependency. Existing uncertain transports are not
replayed and managed lease protection remains intact.

## Executed evidence

RED on parent for missing identity context: 2 FAIL in 4.88s, both conversation and
managed work reached the native fixture without role/capabilities/instructions.
An intermediate assertion used the wrong SQLite column name `envelope_json`:
2 FAIL in 4.89s; corrected to the existing `envelope`. That intermediate failure
is a test defect, not another behavioral reproduction.

Bootstrap integration before 046:

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_bootstrap.py tests/test_runtime_contracts.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_outbox.py tests/test_runtime_result_publication.py
47 passed in 87.51s

rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_bootstrap.py tests/test_runtime_handoff_dispatch.py
13 passed in 37.66s
```

Creation-authority RED with bootstrap already present:

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_dispatch.py -k policy_changed_after_creation
2 failed, 11 deselected in 5.44s
```

Final integrated gates (bootstrap + 046):

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_handoff.py tests/test_handoff_dependencies.py tests/test_verification.py tests/test_hitl.py tests/test_runtime_handoff_epochs.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_bootstrap.py
227 passed, 1 warning in 70.54s

rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_handoff_dispatch.py tests/test_runtime_bootstrap.py
18 passed in 50.06s

rtk proxy ruff check src/okto_nexus/application/runtime_bootstrap.py src/okto_nexus/application/runtime_delivery.py src/okto_nexus/application/runtime_work.py src/okto_nexus/domain/delivery.py tests/test_runtime_bootstrap.py
All checks passed

rtk proxy ruff check src/okto_nexus/application/handoff.py tests/test_runtime_handoff_dispatch.py
All checks passed
```

Warning is upstream Starlette TestClient/httpx deprecation. All integrations use
production HTTP/MCP/REST/serve composition and fixture native peers. No model or
personal session was called; native validation for this unit is NOT_RUN.
These counts are fresh scoped runs, not a whole-plan matrix certification.

Mapping: F01/F06/F13 safe canonical bootstrap; F02/F07 unchanged creation
authority across managed admission and transport. Partial T-WORK-04 and
T-AUTH/T-TX evidence, with child credentials and native HITL still unfinished.
