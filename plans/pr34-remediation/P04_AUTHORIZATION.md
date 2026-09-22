# P04 — scoped runtime authority (in progress)

Parent SHA: `dc67cdd`, branch `feature/v0.2.0`.

Migration 031 persists credential-bound, expiring grants and access audit.
RuntimeAccessService checks the current canonical Agent, credential hash,
communication permissions and bidirectional tag scope. Grants constrain an
exact represented Agent, endpoint, workspace, profile revision, action set and
execution budget. Changing a key or profile invalidates prior delegation.
Grant issuance and revocation require authenticated operator authority.

POST /api/v1/harness/grants issues a grant; DELETE /api/v1/harness/grants/{id}
revokes it. The response never returns the credential binding. Delegated open
requires an explicit endpoint selector. A client cannot obtain authority by
supplying actor/grant/native configuration fields in a conversational payload.
RuntimeControlService revalidates authorization immediately before send/steer
and reserves budget under SQLite's write lock, before calling the connector
outside the transaction. Attempts consume budget conservatively; a transport
timeout is not permission to replay. Steer also consumes execution budget.

REST and MCP use the same access/control services. Existing stdio authentication
through OKTO_NEXUS_API_KEY is reused; absent identity remains unauthorized.
Native children never receive that key. The stdio test deliberately uses a
disposable non-operator fixture key in a separate Nexus process, not a harness.

Evidence:

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_grants.py -q`
  — 11 PASS at that revision, evidence/p04-grants.log, including real stdio.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_grants.py tests/test_runtime_endpoints.py tests/test_import_boundary.py tests/test_pr34_remediation.py -q -k 'not replay_keeps and not one_delivery and not forward_preserves and not terminal_storage and not expired_relay and not open_does_not_fabricate and not committed_delivery'`
  — 59 PASS, 7 explicitly deselected; evidence/p04-progress.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_grants.py -q -k 'concurrent_grant or wrong_endpoint'`
  — two additional tests PASS, evidence/p04-boundaries.log. Concurrent budget
  admits one send; unknown and inaccessible resources return identical denials.
- Ruff on changed application, inbound, repository and test modules: PASS.

The first integration run rejected four legacy tests that sent both text and
content. Tests now use the appropriate native text field for each connector;
public conversational input deliberately has one field and no native options.

Remaining gate dependencies: enqueue/dispatch revalidation and stable idempotency
(P05/P06); handoff/claim-scoped execution and native HITL (P09); post-acceptance
publication authority (P08/P09); endpoint/admin discovery and complete tool/schema
parity (P11). Raw supervisor methods are low-level lifecycle primitives; external
controls compose RuntimeControlService. Native connector campaign still NOT_RUN.
P04 remains IN_PROGRESS; these results do not assert the final enabled gate.
