# Runtime administration — surface 39

This reference describes the implemented 0.2.0 administrative subset. The release
and complete P11/P12 gates are still pending; consult the
[execution status](../../plans/pr34-remediation/IMPLEMENTATION_STATUS.md).

Enable `OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS=true` explicitly. Authenticate as
the operator using the existing Nexus authentication mechanism. An agent ID in
the body cannot supply operator authority. These operations configure existing
agents' connections; they never register or replace the Agent profile. Configuring
an endpoint does not itself spawn a process.

`harness_list` keeps the same tool name. Its `view` selects `adapters`, `endpoints`,
`profiles`, `journal` or `artifacts`. `maintenance` is an object (or JSON object
string); its `action` defaults to `list` for endpoint/profile views. Do not pass
`compact` outside the journal view.

| MCP view/action | REST equivalent | Required parameters in maintenance |
|---|---|---|
| profiles/list | GET /api/v1/harness/profiles | None |
| profiles/create | POST /api/v1/harness/profiles | profile_id, adapter_id |
| endpoints/list | GET /api/v1/harness/endpoints | None; agent_id is an optional filter |
| endpoints/create | POST /api/v1/harness/endpoints | endpoint_id, agent_id, adapter_id, project_root; profile_id for managed processes |
| endpoints/update | PATCH /api/v1/harness/endpoints/{id} | endpoint_id, expected_revision, public_config |
| endpoints/boot | PUT /api/v1/harness/endpoints/{id}/boot | endpoint_id, expected_revision, enabled |
| endpoints/reconcile | POST /api/v1/harness/endpoints/{id}/reconcile | endpoint_id, expected_revision, idempotency_key, reason, acknowledge_uncertain_effects=true |

REST bodies omit `action` and path-bound `endpoint_id`. Both surfaces use the same
input models and application services. Unknown fields and implicit type coercion
are rejected: send JSON `true`, not the string `"true"`. Revisions must be positive
integers. Surface 39 makes this validation explicit; clients caching older schemas
should refresh `nexus_info`. Reference resource `tool-docs/identity` is version 6.

List responses use `{ok:true,data:{items:[...]}}`. Profile discovery omits command
paths, environment values and secret reference names. It exposes the profile ID,
adapter, enabled/inherit-ambient switches, revision and supported non-sensitive
configuration fields. The listing does not resolve secrets.

Profile creation defaults to disabled and `inherit_ambient=false`. Only an
approved profile may back a managed endpoint. Backend configuration belongs to
the profile; opening a session cannot override it arbitrarily. Configure dedicated
tool homes through supported profile environment fields when needed. Do not put
raw credentials in the payload; never forward the Nexus operator key to a child.

For an existing `worker` Agent and enabled `approved-codex` profile:

```json
{
  "view": "endpoints",
  "maintenance": {
    "action": "create",
    "endpoint_id": "worker-code",
    "agent_id": "worker",
    "adapter_id": "codex",
    "project_root": "/approved/project",
    "profile_id": "approved-codex",
    "enabled": true,
    "response_policy": "conversation"
  }
}
```

Use an actual absolute local project path. Endpoint creation also accepts priority,
selection_group, consumption and public_config. Public configuration supports
explicit notification targets and opt-in bounded result relay where correlated
results are supported. `update` replaces that entire public configuration; removing
notify_target restores the private correlated reply destination. A stale revision
fails with `CONFLICT`, rather than overwriting a newer decision.

Boot requires a current enabled profile and endpoint. Attach cannot use a saved
PID as boot authorization. Reconciliation requires a quarantined endpoint without
an active ready/closing runtime, an explicit reason and acknowledgement of uncertain
prior effects. Retrying the same reconciliation through either surface returns
the same reconciliation ID. It does not resend an ambiguous delivery or invent
native completion.

The existing journal/artifact maintenance actions remain available. Profile
editing/disable, broader endpoint editing, outbox takeover, capability negotiation
and dashboard diagnostics are not delivered by this subset and remain tracked in
P11. Deleting persistence rows is not an operational substitute for those actions.
