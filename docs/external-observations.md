# External observations (protocol 1)

External observations describe activity of an explicitly registered external
instance. They do not create an executor, open a coordination session, accept a
handoff, answer an approval, run a model turn, free capacity, or establish task
success. MCP-only participation continues independently.

`feature_observations` is opt-in and defaults to `false`. Configure it through
the existing settings API or `OKTO_NEXUS_FEATURE_OBSERVATIONS=true`. Disabling
ingestion preserves authorized historical reads; their projected freshness is
`unavailable`. Runtime, harness integrations, attention and OBS have separate
switches.

## Register and approve

Use the existing human operator session, trusted local operator path, or
canonical operator key for management under `/api/v1/observations`. Browser
session writes retain the existing same-origin/CSRF checks. A publish token
never authenticates management requests.

1. Select an existing agent and existing workspaces. Set its technical
   `observations.publish` permission explicitly to JSON `true`. Optionally set
   `observations.manage_self=true` to let that agent manage instances and tokens
   inside its approved sources. Both permissions default to false, including
   legacy identities and built-in permission presets. These are permission
   flags, not routing capabilities or skills.
2. `POST /api/v1/observations/sources` with:

   ```json
   {
     "agent_id": "existing-agent",
     "source_kind": "custom",
     "workspace_ids": ["existing-workspace"],
     "registration_ref": "caller-generated-registration-reference"
   }
   ```

   Supported kinds are `herdr`, `hook`, and `custom`. The response contains a
   Server-issued `source_id` and `revision`. Repeating the same registration
   reference and original consent recovers the same source. Reusing that
   reference for different consent conflicts. Names, panes, directories and
   hostnames never establish identity or workspace authority.
3. `POST /api/v1/observations/sources/{source_id}/instances` with:

   ```json
   {
     "expected_revision": 1,
     "workspace_id": "existing-workspace",
     "external_instance_ref": "opaque-installation-and-occupant-reference"
   }
   ```

   Keep the returned `observed_instance_id` and `generation`. The same source,
   workspace and external reference recover the existing instance without
   resetting its sequence or generation. Independent instances have independent
   state, even when they belong to the same agent.
4. `POST /api/v1/observations/sources/{source_id}/tokens` with:

   ```json
   {
     "expected_revision": 1,
     "instance_grants": [
       {"observed_instance_id": "returned-instance-id", "generation": 1}
     ]
   }
   ```

   Use the actual generation returned by the Server. Each credential has 1–100
   immutable instance/generation grants within one source. Workspace IDs are
   resolved by the Server. Issuance requires the represented agent's current
   explicit publish permission, including when an operator issues it.

The returned opaque `nxobs_` token is shown once. Store it as a secret; the
Server stores its SHA-256 hash only. It expires after 15 minutes. Pass it only
as `Authorization: Bearer <token>` to the exact
`POST /v1/observations/activity` path. Query keys, `x-api-key`, human cookies,
canonical agent keys, EPT read tokens and execution capabilities cannot
substitute for this bearer. The OBS bearer is rejected on every other audience,
including MCP, messages, handoffs, runtime and credential issuance.

## Publish a fresh snapshot

```json
{
  "schema_version": 1,
  "source_id": "returned-source-id",
  "observed_instance_id": "returned-instance-id",
  "generation": 1,
  "sequence": 42,
  "state": "blocked",
  "evidence": "inferred",
  "observed_at": "2026-11-06T12:00:00Z",
  "valid_for_seconds": 90,
  "reason_code": "external_input_required"
}
```

Use actual IDs, generation, current observed time and a monotonically increasing
sequence. Exact JSON types and a closed schema are required. States are
`working`, `idle`, `blocked`, and `unknown`; evidence is `reported` or `inferred`.
Optional fields are `reason_code`, `reason_text` (512 characters maximum), and
`current_completion_ref` (an opaque printable reference, at most 256 characters).
Reason codes are `external_input_required`, `external_activity`, `external_idle`,
`external_completion`, `external_error`, `source_unavailable`, and `unknown`.
No agent/workspace/session IDs, prompts, frames, logs or arbitrary fields are
accepted in reports. Explanatory text is untrusted display data.

An optional completion reference describes an externally observed completion;
it has no handoff or task-result meaning. Idle or a completion reason without a
reference does not invent a completion event. The latest non-null reference is
retained across continuity reports that omit it. Observers must derive new
references from actual occupant-specific evidence, not from focus, startup or
an idle snapshot.

A single report is limited to 4 KiB, both as supplied and after canonical
normalization (including the default TTL and normalized UTC precision). A batch is
`{"reports": [report, ...]}` with at most 100 distinct instances and a bounded
request body. The entire batch commits or fails together. Each report counts
toward quotas; the default source burst of 20 means a batch larger than 20
requires an explicitly increased burst. Byte, cardinality and rate limits are
independent.

The success response contains receipts with `observed_instance_id`,
`generation`, `sequence`, `report_hash`, `received_at`, `valid_until` and
`replayed`. State, quota and material events commit in one transaction before
success is returned. Storage errors never acknowledge an uncommitted report.

- Same latest sequence and canonical hash returns its original receipt, without
  renewing validity or emitting another event. Current authorization is checked
  first, even for replay. Duplicate attempts still consume ingress/report quota.
- Same sequence with a different hash, an older sequence, or a mismatched
  generation conflicts. Neither sequence nor generation wraps around.
- `valid_until = min(received_at + TTL, observed_at + TTL)`. Expired backlog is
  rejected. Future skew defaults to at most 30 seconds and never extends the
  TTL past receipt time plus TTL.
- Omitted TTL is a fixed protocol default of 90 seconds. The configurable
  maximum applies to new reports. Reducing the maximum below 90 requires an
  explicit smaller TTL on new reports; already accepted exact replay remains
  recognizable under its original hash.
- Reconnect by reading a fresh source snapshot. Do not replay a historical
  backlog as current activity. A publisher that cannot prove continuity must
  obtain an authorized new generation instead of restarting sequence at one.

## Read, renew, revoke and retire

`GET /api/v1/observations` accepts `agent_id`, `workspace_id`, `source_id`, `after`
and `limit` (1–200). Operator reads may span sources; a canonical self-manager
sees only its own. `next_after` is the page cursor. GETs are passive: they do not
touch presence, credentials, TTL, capacity, business state or seen status.

Each instance exposes its provenance and a `last_report`, separately from its
current projection. Freshness is `current`, `stale`, `unknown`, or `unavailable`.
Expired data is stale, never inferred idle or canonical offline. Revoked
authority, a disabled feature/source, or changed source scope makes retained
data unavailable. Source continuity is a separate age diagnostic across its
instances, not proof that a process died. There is no implicit canonical-session
correlation; an external instance remains distinct.

Source detail/list endpoints are `/sources` and `/sources/{source_id}` under the
management base. The latter's `/instances` and `/tokens` endpoints list
registrations and credential metadata. They never return raw token hashes or
recover a bearer. These lists support `after` and `limit`.

- Operator source updates use `PATCH /sources/{source_id}` with
  `expected_revision` and `enabled` and/or `workspace_ids`. Material consent
  changes advance the revision and fence old tokens. No-op updates preserve it.
- Operator source revocation uses `POST /sources/{source_id}/revoke` with
  `expected_revision`.
- Renew through the canonical token-issuance endpoint, supplying current source
  revision and exact instance generations. Optional `replaces_token_id` revokes
  the previous token atomically with issuance. The old publish token cannot
  renew itself. After a lost issuance response, list/revoke credential IDs and
  issue a replacement; no bearer is stored for response replay.
- Revoke a credential with `POST /sources/{source_id}/tokens/{token_id}/revoke`.
- A new occupant requires `POST /sources/{source_id}/instances/{id}/rotate`
  with `expected_revision` and `expected_generation`, followed by a new token
  grant. The previous token cannot publish for the replacement occupant.
- Retire with the corresponding `/retire` endpoint and the same CAS fields.
  Cleanup remains possible after disabling/revoking the source. Retired IDs and
  generations are never reassigned.

Agent deactivation, key replacement/removal, retirement, and effective changes
to either explicit OBS permission permanently revoke outstanding tokens.
Restoring an earlier key or permission does not revive them. Unrelated or
no-op permission changes do not revoke them.

## Bounds and maintenance

Initial configurable defaults are proposals, not measured deployment capacity:

| Setting | Default |
|---|---:|
| Maximum report TTL / future tolerance | 3,600s / 30s |
| Source continuity diagnostic threshold | 30s |
| Reports per minute / burst, source | 60 / 20 |
| Reports per minute / burst, agent | 1,920 / 80 |
| Reports per minute / burst, installation | 8,192 / 512 |
| Sources per agent / installation | 32 / 4,096 |
| Instances per installation | 4,096 |
| Live credentials per source | 8 |
| Observation event retention / row cap | 7 days / 20,000 |

The settings catalog exposes the corresponding `observation_*` fields and
their safe configuration bounds, with matching `OKTO_NEXUS_OBSERVATION_*`
environment variables. A process-local ingress guard holds at most 32 pending
OBS writes, before HTTP body reads and worker/writer queues. Durable budgets
aggregate by source, agent and installation across tokens. Exhaustion returns
429 with `Retry-After`; queue saturation/storage unavailability returns 503.
Bounded HTTP bodies have a five-second read timeout.

Continuity updates replace a head without creating a heartbeat log. State,
blocking and completion changes produce private `observation.*` events in the
existing event store. Existing retention maintenance (`admin prune`, including
dry-run and bounded startup pruning) cleans OBS history and obsolete credentials
and buckets. Live instance sequence/hash barriers are retained after TTL expiry.
Tokens referenced by heads remain until their evidence is replaced or retired.

A history reset preserving agents retains source approval configuration but
removes observation instances, tokens and heads. Re-registration issues new
instance IDs and larger generations. The installation generation counter
survives both reset modes; an old credential/report cannot cross the reset.

This Server contract requires no Herdr installation or Connector daemon.
The optional Herdr observer and attention integration are separate milestones.
