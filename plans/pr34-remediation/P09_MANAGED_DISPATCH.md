# P09 — canonical managed claim and dispatch

Execution date: 2026-09-23. Parent SHA: `3d3f9263f6cb506752140b5bb4a65bcc41779cac`.
Implementation is the subsequent commit containing this document. P09 remains
IN_PROGRESS and the final gate has NOT PASSED.

## Contract and composition

Migration 045 adds `runtime_handoff_bindings`, an immutable link between a
canonical handoff claim generation, explicit execution grant and existing
delivery outbox operation. It is not another work queue. No existing migration
was edited and no personal database was migrated.

`HandoffService.handoff_claim` now accepts `runtime_endpoint_id`,
`execution_grant_id`, `idempotency_key` and optional `claim_epoch`. MCP and
`POST /api/v1/workspaces/{workspace_id}/handoffs/{handoff_id}/claim` use that same
service. Surface revision is 37. Unmanaged claims retain their session trust
rules; the shared composition enforces these in REST and MCP. Managed claims
require authenticated identity plus an explicit `execute_work` grant, including
for an operator caller. A conversation `send` grant is insufficient.

For an OPEN handoff, omit claim_epoch. For a claim already owned by the selected
logical agent, pass its observed epoch. The canonical claim, grant charge,
single synthetic inbox delivery, push reservation, transport intent and binding
commit atomically. The dispatcher uses existing bounded workers and revalidates
the claim, grant, credentials, endpoint/profile revisions and canonical policies
before native effects. No peer/network/secret call occurs in that transaction.

Retry an admission with its original key and identical arguments. The original
operation and its original claim_epoch are returned; this does not execute a
new rework generation. Other response fields describe the current handoff.
New generation dispatch requires a new key and that generation explicitly.
An existing claim emits `handoff.execution_requested`, not another
`handoff.claimed`. A failed post-commit wake cannot undo admission; bounded
owner reconciliation recovers its durable intent.

Only one execution binding is admitted per claim generation, irrespective of
concurrent callers or endpoint choices. Built-in eventful managed adapters can
carry this operation; attach remains conversation-only without an authenticated
external work channel. This capability does not claim native approval support
or an already implemented subprocess credential bootstrap.

Native terminal output is captured and can produce an authorized private
notification. It never calls handoff_complete automatically. Publication
revalidates managed authority; revocation or a different current claim generation
blocks publication while retaining captured evidence. Explicit canonical
complete/verify/reject still controls work state.

## Recovery and limitations

Any handoff with a managed binding is protected from automatic lease reopening,
including after native terminal, uncertain transport or feature disablement.
The guard is in the SQLite repository, so other service compositions cannot
accidentally expire that lease. Claimant/creator `handoff_get` exposes
`managed_lease_protected` and the current `runtime_execution`; `harness_get`
accepts the outbox operation ID under existing read authorization.

This conservative protection also holds for proven-unsent failures. Do not
manually delete the binding or replay the transport. Explicit safe administrative
reconciliation/reassignment is a remaining P11 dependency. Restricted runtime
credentials/bootstrap, native HITL, causal relay and the full final campaign are
still pending. No new real provider run occurred in this unit; all external peers
were fixtures. Pi and dedicated attach native remain NOT_RUN by current scope.

## Evidence

Tests use real HTTP authentication, MCP, REST and production serve dispatcher;
only native peers are synthetic. `tests/test_runtime_handoff_dispatch.py` covers
atomic rollback after enqueue, concurrent idempotency, grant isolation, strict
trust parity, native result/explicit completion, expired lease protection,
revocation before write and late publication after revocation/rework.

Behavioral RED on parent: managed parameters were silently ignored and ordinary
claim succeeded without a grant (`test_managed_claim_cannot_silently_fall_back_to_unmanaged_claim`):
1 FAIL in 2.48s. The corrected flow denies and leaves the handoff OPEN.

Commands executed (all shell commands prefixed with `rtk`):

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_dispatch.py tests/test_runtime_handoff_epochs.py
14 passed, 1 warning in 21.68s

rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_handoff.py tests/test_handoff_dependencies.py tests/test_verification.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_handoff_epochs.py tests/test_runtime_result_publication.py tests/test_runtime_grants.py tests/test_comm_presets.py tests/test_feature_flags.py tests/test_health.py tests/test_memory.py tests/test_replay_marker.py
360 passed, 1 warning in 118.12s

rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_handoff_dispatch.py tests/test_runtime_handoff_epochs.py tests/test_runtime_result_publication.py
23 passed, 1 warning in 63.05s

rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_dispatch.py -k late_managed
2 passed, 9 deselected in 7.93s

rtk proxy ruff check src/okto_nexus/application/handoff.py src/okto_nexus/application/runtime_work.py src/okto_nexus/application/runtime_access.py src/okto_nexus/application/runtime_control.py src/okto_nexus/application/runtime_results.py src/okto_nexus/adapters/inbound/mcp/tools/handoff.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/adapters/inbound/mcp/tools/messages.py src/okto_nexus/adapters/inbound/http/routes.py tests/test_runtime_handoff_dispatch.py tests/test_pr34_remediation.py
All checks passed
```

The two late-publication cases were added after the 360/23-test collections;
their Linux run is NOT_RUN for this checkpoint. Warning: upstream Starlette
TestClient/httpx deprecation. An initial command named nonexistent
`tests/test_runtime_handoff_auth.py`: collection exited 4, no tests ran; it is
not a RED reproduction or coverage evidence.

Mappings: F02 authorization parity, F03 one executor, F04 durable intent,
F07 canonical work, F13 grant isolation. Partial T-WORK-01/03/05/06/07 and
T-TX coverage only; the full competitive multi-agent/multi-endpoint matrix,
authenticated child completion and native approval gates are not certified here.
