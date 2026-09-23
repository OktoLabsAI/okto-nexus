# P10 — explicit notification audience and bounded fanout

Date: 2026-09-23. Parent SHA `6540cd7`, branch `feature/v0.2.0`.
The containing commit identifies this unit. P10 final gate remains pending.

## Implemented contract

`EndpointService.validate_public_config` accepts optional `notify_target` using
the existing target grammar and inbox deliverability restrictions. The default
is still a private reply to the source message sender. Explicit direct, role,
capability, tag, mixed and broadcast targets reuse canonical MessageService
resolution, catalog checks, presence, permissions, audiences, governance and HITL.
No target is taken from model output. Null/removal restores the private default.

`PATCH /api/v1/harness/endpoints/{endpoint_id}` accepts a full replacement
`public_config` and strict positive `expected_revision`. Shared admin authorization
runs before lookup; CAS/revision protects against stale edits. This is an initial
endpoint-update use case; full MCP administration and remaining CRUD belong to
P11 and are NOT claimed complete here. Creating an endpoint supports the same
configuration and validator. Configuration is bounded to 64 KiB.

`RuntimeOpenService.open` now rejects a supplied `notify_target` differing from the
approved endpoint configuration before constructing a connector. Previously that
argument could be accepted while production result publication ignored it. A
matching value is supported; omission uses approved endpoint configuration.
Neither operation alters canonical Agent identity/profile.

`RuntimeResultService.row/arguments` derives the destination from the bound source
endpoint. Existing source revision checks prevent an old result from adopting a
new configuration silently. Artifact readers are precisely the represented sender
plus the resolved authorized recipients, not all agents or the default caller
when an explicit destination excludes that caller.

For dissemination outside the original private reply, the originating actor's
current permissions, recipient limit, audience and governance also apply. This
intersects with the represented sender's ordinary canonical checks. The actor's
governance revision joins the transport authorization snapshot; permissions and
audience are rechecked before dispatch. A new actor HITL policy after turn admission
can intercept result publication; a later grant of permission is not assumed.
Private replies retain the original conversation semantics and do not require
an actor to address itself through an outbound audience selector.

Explicit `relay_results=true` remains separately necessary to start conversation
turns from published results. Without it, broadcast observers receive the logical
notification only. With it, one generated result message can reserve one execution
per logical recipient, each on one endpoint, within the shared root budget. The
message budget is charged once, execution budget once per admitted recipient.
Partial admission is explicit; it never creates another work queue or handoff.

Migration 052 adds `runtime_relay_decisions`, an admission audit referencing the
existing result, inbox delivery and optional outbox operation. `ENQUEUED`, `BLOCKED`
and `NO_ENDPOINT` are per-recipient facts; aggregate `PARTIAL` means some recipient
relays were admitted and others were not. It is not external acceptance. Blocked
admission emits a persisted sender-scoped `runtime.relay_blocked` event, not another
message/turn. Retention keeps these audit references and their inbox rows intact.

## Additional confirmed governance defect

`message_action_for` previously compared the raw discriminator to lowercase
`broadcast`, while routing accepted canonical aliases/case variants. The new
negative test demonstrated a forbidden `BROADCAST` result reaching two inboxes
with state PUBLISHED. This was an actual behavior failure, not a missing import.
The shared governance classifier now calls `domain.targets.target_strategy`, so
all surfaces use the same normalization. No duplicate target parser was added.

## Executed evidence

All peers/stores are disposable fixtures; no provider/model or personal store used.
Separate run counts below are not additive coverage totals.

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py -x`
  — initial 6 PASS, 19.86s (broadcast/removal, direct/role, sender denial, authority,
  and artifact readers).
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py tests/test_runtime_relay.py`
  — 30 PASS, 96.37s (before additional origin-authority cases).
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py -k 'commit_cut or stale_configuration'`
  — 2 PASS, 9 deselected, 6.17s. Commit cut rolls back every child, decision and
  quota reservation; after repair exactly two peer sends occur. Stale update denied.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py tests/test_runtime_result_publication.py tests/test_retention.py`
  — 49 PASS, 73.86s (intermediate origin checks, before final revision snapshot).
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py -k 'borrow or originating or broadcast_relay'`
  — 3 PASS / 1 FAIL, 14.47s: authoring error used unsupported governance action
  `message_broadcast`; corrected to canonical `broadcast`.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py -k originating`
  — first 1 PASS / 1 FAIL, 7.21s: require_approval supports message_create, not
  broadcast directly. Corrected test installs message_create approval at the
  deterministic post-turn-admission/pre-publication boundary. Then 2 PASS,
  12 deselected, 8.74s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py -k private_reply_does -x`
  — 1 PASS, 14 deselected, 5.44s. Suspected self-audience restriction was NOT
  reproduced: existing reachability already permits this legitimate private path;
  no planner relaxation was needed.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py -k 'broader_notifications and BROADCAST' -x`
  — behavioral RED: 1 FAIL / 1 PASS, 14.14s, uppercase discriminator bypasses deny.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_notify_targets.py -k broader_notifications tests/test_governance.py`
  — after classifier fix 2 PASS, 55 deselected, 9.35s. This filtered command did
  not execute the full governance file; the full command follows.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_governance.py tests/test_runtime_notify_targets.py`
  — final Windows 58 PASS, 85.41s, one existing Starlette/httpx deprecation warning.
  Includes current origin revocation before fanout: both child attempts REJECTED,
  no native observer sends; publication and captured result retained.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_notify_targets.py tests/test_runtime_relay.py`
  — intermediate Linux 34 PASS / 1 FAIL, 117.13s: same unsupported approval action
  in the test version collected before the correction; no implementation failure.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_notify_targets.py`
  — final Linux 17 PASS, 80.08s.
- Ruff over every changed Python file and `rtk git diff --check` — PASS.

## Operation and recovery

Use an operator-authenticated endpoint create/update, for example this PATCH body:

```json
{"expected_revision":1,"public_config":{"notify_target":{"strategy":"broadcast"}}}
```

The configuration replacement must retain other intended fields, including
`target_pid` for attach or `relay_results` if explicitly desired. To restore the
private default, replace with `{}` (or remove notify_target while retaining other
fields), using the current revision. Revision changes fence prior intents/results
and invalidate old boot authorization; review/reconfigure boot before reuse.
No in-flight operation is automatically replayed against the new audience.

Apply additive migration 052 normally. Do not delete decision/inbox/outbox/causal
rows to force retries. Retention protects the references. Backup/restore must
preserve them with the result/journal; full restore campaign is still a P12 gate.
Failure before publication commit causes no child native send; admission recovery
reuses the source result and has no duplicate budget charge.

Native notify-target campaign remains NOT_RUN. Remaining P10 includes whole-process
restart/cuts, expanded target/policy matrices and aggregate gate review. P11 still
needs complete MCP/admin/UI/capability work; P12 full matrix/build/install remain.
This unit does not certify those phases or the final gate.
