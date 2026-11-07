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

Management responses use the existing `{"ok": true, "data": ...}` envelope.
Keep `data.source.source_id` and its current `revision`, then
`data.instance.observed_instance_id` and its Server-issued `generation`. Token
issuance returns `data.token` once and `data.credential` with its `token_id`,
`expires_at`, and approved grants. Keep credential metadata separate from the
secret. The numeric values and IDs above are placeholders, not values to infer
from an agent name or external process.

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

## Use the publish-only Python helper

`okto_nexus.observation_client` is included in the Nexus package and uses the
Python standard library. It needs no Connector, framework, native runtime or
background process. Complete registration and token issuance above before using
it. The `nxobs_` credential authorizes only publication; it cannot authenticate
MCP, native execution, management, token renewal or canonical agent operations.

Persist a complete report before sending it. The saved document must contain the
approved IDs and generation, its sequence, and the time of the actual
observation. Keep the bearer outside that document. For example, with an
explicitly chosen secret environment variable and a saved report:

```python
import json
import os
import sys

from okto_nexus.observation_client import ObservationClient, ObservationClientError

with open("saved-observation.json", encoding="utf-8") as saved:
    pending_report = json.load(saved)

try:
    publisher = ObservationClient(
        os.environ["NEXUS_SERVER_ORIGIN"],
        token=os.environ["MY_OBSERVATION_PUBLISH_TOKEN"],
        timeout=15,
    )
    acknowledged = publisher.publish(pending_report)
except ObservationClientError as error:
    print(json.dumps({
        "code": error.code,
        "status": error.status,
        "outcome_unknown": error.outcome_unknown,
        "retry_after_seconds": error.retry_after_seconds,
    }), file=sys.stderr)
    raise SystemExit(2) from None

print(json.dumps(acknowledged))
```

`publish` accepts a single report dictionary, a list of 1–100 reports, or the
saved `{"reports": [...]}` wrapper. It validates the closed schema, both input
and canonical 4 KiB limits, and distinct instance IDs before network I/O. It
never fills in generation, sequence or observed time, and never increments or
resets them. A successful return is `{"receipts": [...]}` containing only the
validated receipt fields listed above, in report order. The helper checks IDs,
generation, sequence, canonical hash and receipt validity against the submitted
report. It accepts a historical replay receipt whose expiry has already passed;
that receipt does not make the observation fresh again.

The runnable [stdin example](observation-client-example.py) uses the same API:

```sh
python docs/observation-client-example.py --origin https://nexus.example \
  --token-env MY_OBSERVATION_PUBLISH_TOKEN < saved-observation.json
```

The argument names the environment variable; never substitute the bearer as an
argument. The script prints validated receipt metadata on stdout and sanitized
errors on stderr. The helper accepts HTTPS origins or loopback HTTP origins,
without credentials, application paths, queries or fragments. It ignores
environment proxies and does not use redirects, cookies or netrc credentials.
Its finite timeout defaults to 15 seconds and may be set up to 30 seconds.

### Preserve uncertainty and replay explicitly

The helper makes one POST per `publish` call. It has no retry loop, scheduler,
heartbeat, generation allocator or credential-renewal method. The caller owns
durable sequence allocation per instance/generation and the saved payload across
restart. Record a validated receipt before discarding that pending payload.

If `outcome_unknown` is true, the Server may already have committed the report.
Keep the same pending document. An explicit retry sends that exact intent with
the same IDs, generation, sequence, observed time, TTL and contents. Do not
increment the sequence, change the timestamp, rotate generation or create a new
source merely to hide the uncertain result. Exact replay recovers the original
receipt without extending its validity. If a later sequence has already been
accepted, the old attempt conflicts; it cannot recover arbitrary historical
receipts. Inspect the authorized current state and retained caller checkpoint.

Replay grants no new authority. The Server rechecks the current token, source,
agent, workspace and generation first. If a credential has expired, its
replacement must be issued through the existing authorized management path;
the pending document remains unchanged. A new credential does not revive a
revoked source, restore removed permission or bypass a changed generation.

| Result | Meaning and caller action |
|---|---|
| Local `REPORT_INVALID`, `TOKEN_INVALID`, `SERVER_ORIGIN_INVALID`, `TIMEOUT_INVALID` | No request was sent. Correct the local input before an explicit submission. |
| HTTP 401 / `AUTH_FAILED` | The credential or authentication audience was refused. Use the authorized publish credential for this endpoint. |
| HTTP 403 / `PERMISSION_DENIED` | Publication is unauthorized, including expired/revoked credentials, revoked source or identity, removed permission, or an unapproved scope. Stop publishing and inspect current authorization. |
| HTTP 409 / `CONFLICT` | Generation or sequence/content may conflict; ingestion may also be disabled. Inspect the canonical source/instance state and original pending payload. Do not auto-reset or acquire new authority. |
| HTTP 413 / `CONTENT_TOO_LARGE`, HTTP 422 / `VALIDATION_ERROR` | The request was refused. Fix the report or its size before explicitly submitting corrected input. |
| HTTP 429 / `QUOTA_EXCEEDED` | Publication quota was exhausted. `retry_after_seconds`, when supplied, is advisory and capped at 3,600 seconds. The helper does not retry. |
| HTTP 503 / `OBSERVATION_BUSY` | A recognized queue-saturation response refused admission; no automatic retry occurs. |
| Generic HTTP 503 / `OBSERVATION_UNAVAILABLE`, transport loss, invalid receipt, or refused redirect | `outcome_unknown=true`. Preserve the pending payload; the response does not prove that no report committed. |

`ObservationClientError` exposes `code`, `status`, `outcome_unknown`, and
`retry_after_seconds`. Remote response text, supplied report contents and bearer
values are not copied into those errors. A receipt acknowledges external
telemetry only; it is never evidence that a handoff or model task succeeded.

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

To renew before the 15-minute credential expiry, authenticate as the operator or
an authorized canonical self-manager and call
`POST /api/v1/observations/sources/{source_id}/tokens` again. Use the current
source revision and actual instance generations, for example:

```json
{
  "expected_revision": 1,
  "instance_grants": [
    {"observed_instance_id": "returned-instance-id", "generation": 1}
  ],
  "replaces_token_id": "previous-credential-id"
}
```

Retain the new `credential.token_id` and `expires_at`, install the new bearer in
the publisher's secret channel, and construct a new `ObservationClient` with
that bearer. Renewal preserves instance generation and sequence history. It does
not resend observations or extend an existing receipt's TTL. Source revision or
generation conflicts require reviewing the current authorized registration.
After a lost issuance response, the raw new token cannot be recovered: use the
canonical credential metadata list to revoke the uncertain credential and issue
another explicitly authorized replacement.

### Stop a publisher without inventing activity

Shutdown stops publication. Do not synthesize `idle`, a completion reference or
a claim that the observed process died. Preserve the instance identity,
generation, last allocated sequence, pending payload and validated receipt so a
restart can prove continuity. Stopping the observer is not evidence about the
external process's state.

An authorized manager may explicitly revoke the token or source, or retire the
instance through the endpoints above. Those are separate management decisions;
the helper performs none of them. Without revocation, observations become stale
when their TTL expires and source continuity becomes delayed according to its
diagnostic threshold. Revoked authority is projected as unavailable. Neither
case changes canonical presence, releases runtime capacity, completes work or
marks an external application as seen.

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
Tokens referenced by heads or retained completion events remain until those
references are replaced, retired or pruned. This preserves revocation evidence
without retaining the raw bearer.

A history reset preserving agents retains source approval configuration but
removes observation instances, tokens and heads. Re-registration issues new
instance IDs and larger generations. The installation generation counter
survives both reset modes; an old credential/report cannot cross the reset.

This Server contract requires no Herdr installation or Connector daemon.
The optional [Herdr observer](herdr-observer.md) publishes through the same
restricted ingress.

## Attention and external activity

When attention is enabled, external reports can produce three observational
occurrences. `external_blocked` describes a current report of blocked activity;
its only action is to inspect the instance in its source environment.
`external_completion_unseen` retains a reported completion reference until seen,
subject to event retention. It is not a Nexus result, successful handoff or
permission to start another turn. `external_observation_stale` indicates that a
previous report expired; it does not declare the process idle or dead.

Repeated reports within one continuous blocked episode preserve seen/snooze.
A renewed block after an expiry gap is a new episode. Completion references
use their retained event identity, so two completions between dashboard reads
remain separate occurrences. Historical events lacking original provenance
remain unavailable rather than receiving invented evidence during upgrade.
Marking an occurrence seen or snoozed changes only Nexus viewing preferences;
it does not mark Herdr as seen or alter the observed application.

The Agents view shows external instances separately from canonical presence
and capacity. Its aggregate counts cover the complete authorized scope, while
the expanded instance list is paginated. Only current observations contribute
working/idle/blocked activity; expired, absent or unavailable reports contribute
unknown activity. A failed or overdue refresh marks the snapshot out of date.

Canonical read credentials use these additional metadata endpoints:

- `GET /api/v1/observations/summary` accepts optional `agent_id`, `workspace_id`
  and `source_id` filters. It returns complete activity/freshness counts and
  per-agent totals in one read snapshot, plus a refresh deadline. It does not
  accept pagination; inability to complete the read returns an error.
- `GET /api/v1/observations/instances/{observed_instance_id}` returns the exact
  current instance projection and refresh deadline. The inspector verifies the
  selected source, agent, workspace and generation before showing it. A removed
  or inaccessible instance returns 404; a changed generation requires selecting
  the new instance explicitly.

An authorized self-manager sees only its own sources. Publisher tokens cannot
read either endpoint. Reads never renew reports, open sessions or repair state.
With OBS disabled, history remains readable with unknown activity and no active
external attention occurrences. Canonical coordination continues independently.

The completion inspector retains the selected historical reference separately
from the latest instance report. Source-provided references and explanations
are displayed as text, never executed as commands or opened as links. Existing
observations remain separate from canonical sessions until an explicitly
authorized, evidenced correlation is established; equal names are insufficient.
