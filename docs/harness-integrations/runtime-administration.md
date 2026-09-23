# Runtime administration — surface 41

This reference describes the implemented 0.2.0 administrative subset. The release
and complete P11/P12 gates are still pending; consult the
[execution status](../../plans/pr34-remediation/IMPLEMENTATION_STATUS.md).

Enable `OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS=true` explicitly. Authenticate as
the operator using the existing Nexus authentication mechanism. An agent ID in
the body cannot supply operator authority. These operations configure existing
agents' connections; they never register or replace the Agent profile. Configuring
an endpoint does not itself spawn a process.

`harness_list` keeps the same tool name. Its `view` selects `adapters`, `endpoints`,
`profiles`, `bindings`, `journal` or `artifacts`. `maintenance` is an object (or JSON object
string); its `action` defaults to `list` for endpoint/profile views. Do not pass
`compact` outside the journal view.

| MCP view/action | REST equivalent | Required parameters in maintenance |
|---|---|---|
| bindings | GET /api/v1/harness/bindings | Optional agent_id, limit (1..100, default50), after_endpoint_id |
| profiles/list | GET /api/v1/harness/profiles | None |
| profiles/create | POST /api/v1/harness/profiles | profile_id, adapter_id |
| profiles/update | PATCH /api/v1/harness/profiles/{id} | profile_id, expected_revision and one or more mutable fields |
| endpoints/list | GET /api/v1/harness/endpoints | None; agent_id is an optional filter |
| endpoints/create | POST /api/v1/harness/endpoints | endpoint_id, agent_id, adapter_id, project_root; profile_id for managed processes |
| endpoints/update | PATCH /api/v1/harness/endpoints/{id} | endpoint_id, expected_revision and one or more mutable fields |
| endpoints/boot | PUT /api/v1/harness/endpoints/{id}/boot | endpoint_id, expected_revision, enabled |
| endpoints/reconcile | POST /api/v1/harness/endpoints/{id}/reconcile | endpoint_id, expected_revision, idempotency_key, reason, acknowledge_uncertain_effects=true |

REST bodies omit `action` and path-bound `endpoint_id`. Both surfaces use the same
input models and application services. Unknown fields and implicit type coercion
are rejected: send JSON `true`, not the string `"true"`. Revisions must be positive
integers. Surface 39 introduced strict validation; surface 40 extends edits.
Clients caching older schemas should refresh `nexus_info`. Reference resource
`tool-docs/identity` is version 8. Surface 41 adds scoped binding discovery.

The `bindings` view is also available to authenticated agents with current
endpoint-scoped `discover` grants. The operator issues those through
`POST /api/v1/harness/grants` with actor_agent_id, endpoint_id,
actions=["discover"] and expires_at (within 24 hours). A grant only restricts
existing policy: the caller must retain events.read and communication reachability
to the represented Agent. Revocation, expiry, key rotation, inactive agents and
changed profile revisions remove visibility. A discovery grant does not allow
open/send/read-content/control; no grants returns an empty agents array.

For example, call `harness_list` with
`{"view":"bindings","maintenance":{"agent_id":"worker","limit":20}}`.
The response groups endpoints under each canonical agent_id and lists its
canonical skill_names without rewriting the Agent. It omits private metadata,
paths, environment, secret references, configuration and notification audiences.
`declared_capabilities` describe the adapter contract; `capability_verification`
is `not_probed`, so this is not binary-version negotiation. A session's
`current_owner_ready_record` means its persisted lifecycle/profile and owner lease
are current. `process_liveness=not_probed` explicitly avoids inferring a live
native process from a stored row.

While has_more=true, pass next_endpoint_id as after_endpoint_id. Cursors only
contain visible endpoint IDs. Each endpoint shows at most ten latest sessions
and sessions_has_more. A scan exceeding 1000 candidate endpoints without finding
the requested page fails with QUOTA_EXCEEDED; narrow agent_id. Reads neither
contact the harness nor resolve credentials or modify presence. REST, MCP HTTP
and authenticated MCP stdio use the same persisted projection.

List responses use `{ok:true,data:{items:[...]}}`. Profile discovery omits command
paths, environment values and secret reference names. It exposes the profile ID,
adapter, enabled/inherit-ambient switches, revision and supported non-sensitive
configuration fields. The listing does not resolve secrets.

Profile creation defaults to disabled and `inherit_ambient=false`. Only an
approved profile may back a managed endpoint. Backend configuration belongs to
the profile; opening a session cannot override it arbitrarily. Configure dedicated
tool homes through supported profile environment fields when needed. Do not put
raw credentials in the payload; never forward the Nexus operator key to a child.

Profile updates accept config, secret_refs, inherit_ambient and enabled. Omission
preserves the existing value; an explicit object replaces the whole object, so
send `{}` to clear secret references. Null is not a clearing operation for these
fields. Profile ID and adapter are immutable. Use enabled=false to retire a
profile without deleting its history or referenced operations.

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
results are supported. Endpoint updates accept public_config, enabled, priority,
selection_group, response_policy, consumption and profile_id. Omitted fields are
preserved. An explicit public_config replaces that entire object; removing
notify_target restores the private correlated reply destination. Null can clear
selection_group; a managed endpoint cannot clear its required profile. Agent,
adapter and workspace are immutable. A stale revision fails with `CONFLICT`.

Every configuration edit atomically revokes affected execution grants and disables
their previously approved boot bindings. Re-enabling a profile/endpoint does not
restore those grants or boot approvals. Issue fresh scoped grants and explicitly
reapprove boot after reviewing the new revision. The configuration audit shares
the existing access log and records actor, resource, old/new revision and changed
field names, never configuration or secret values. Operator diagnostics expose
the latest 100 records as `configuration_changes`.

Editing a profile does not change a running process's environment. Its old session
revision cannot admit new sends, even if the edited profile is later re-enabled.
Close it and open a session with the new profile. Operator interrupt/close remain
available; already accepted work is not silently declared cancelled. Late terminal
events remain durable while publication under the revoked configuration is blocked.
Changing an endpoint to a different profile requires previous sessions to be
stopped/detached and no pending open request; equal numeric revisions of different
profiles do not preserve a grant. Unknown sessions require recovery or a separate
explicitly approved endpoint, never reuse based only on a stored PID.

Boot requires a current enabled profile and endpoint. Attach cannot use a saved
PID as boot authorization. Reconciliation requires a quarantined endpoint without
an active ready/closing runtime, an explicit reason and acknowledgement of uncertain
prior effects. Retrying the same reconciliation through either surface returns
the same reconciliation ID. It does not resend an ambiguous delivery or invent
native completion.

The existing journal/artifact maintenance actions remain available. Outbox
takeover, capability negotiation and dashboard diagnostics remain
tracked in P11. Deleting persistence rows is not an operational substitute for
those actions. Migration 053 is additive; operational rollback uses deactivation,
drain and recovery, not reverse SQL or deletion of the audit/history.
