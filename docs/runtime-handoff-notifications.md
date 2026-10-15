# Runtime handoff notifications and automatic broadcast claims

A handoff with `target.strategy="broadcast"` uses one canonical claim. Runtime
candidates reserve capacity for the exact agent, workspace and session affinity
before competing. Only the winner receives `handoff_execute` and the payload.
The availability notice does not invoke a model, including when automation is
disabled or the runtime lacks the required protocol support.

MCP clients continue to read their inbox or query available handoffs and call
`handoff_claim` explicitly. They do not need to publish capacity. Runtime and MCP
claims use the same permissions, eligibility, dependencies and first-claim-wins
transition. A free queue position does not qualify a runtime for an automatic
claim; ordinary messages and explicit claims retain their queue behavior.

Directed handoffs retain their existing runtime notification flow. Other target
strategies are not silently converted to automatic broadcast claims. Ordinary
broadcast messages retain intentional fanout and can produce multiple replies.

## Controlled activation

The server enables automatic acquisition support by default. The startup
setting can explicitly disable it for an installation:

```powershell
okto-nexus serve --runtime-handoff-auto-claim-enabled false
```

The environment equivalent is `OKTO_NEXUS_RUNTIME_HANDOFF_AUTO_CLAIM_ENABLED=false`.
The startup setting does not grant any agent authority. The effective runtime
policy must also enable `broadcast_handoff_auto_claim`, and the agent needs a
current `execute_work` grant for its selected endpoint. Existing conversation
response settings do not imply this opt-in. Finishing connection setup with
effective broadcast automation enabled includes `execute_work` in that
connection's authorization, using its selected duration and action budget.
Existing grants are not silently expanded by a global policy change; existing
connections need an explicit work grant or renewed connection authorization.

The policy is available through the existing operator-authorized runtime policy
API: `GET`/`PUT /api/v1/runtime-policy` for global defaults, or
`GET`/`PUT /api/v1/agents/{agent_id}/runtime-policy` for an agent override.
Use the current `expected_revision` and preserve the other policy fields when
saving. An agent override of `null` inherits the global default; `false` disables
automatic claims for that agent. This policy update does not require a restart.

In the dashboard, use Settings → Global runtime defaults → Automatically claim
broadcast handoffs. Agents → Connections exposes the same option with an
independent inherit/enabled/disabled override. Agent edits stay in the draft and
commit with Finish, under the connection's revision checks and transaction.
The UI identifies a disabled startup rollout gate separately from the saved
preference. Enabling the preference does not create an execution grant.

The optional `broadcast_handoff_auto_claim` field on the connection setup
request belongs to the Server policy, outside the portable harness configuration.
Omitting it preserves existing policy; explicit `null` restores inheritance.
Technical connection exports do not transfer this automation authorization.

## Dashboard execution history

Broadcast handoff cards and details show execution progress separately from the
canonical status. A successful native final leaves the handoff awaiting its
authenticated decision. Verification remains `VERIFYING`; uncertain delivery
appears as reconciliation, and a native failure does not fabricate a business
rejection. Only the binding for the current claim epoch contributes receipts.
With startup acquisition disabled, open work is shown as available for explicit
claim. Missing creator-session provenance is identified as the fallback used
by source-session isolation.

Agents → Runtime administration includes a collapsed list of the 20 most
recently updated broadcast attempts. It shows refusal/recovery reasons and the
last recorded reservation report with its observation time. Consumed admission
reports supersede the earlier reserve report. These are historical observations,
not a promise of current free capacity; reading the panel does not reserve,
claim, release, dispatch or acknowledge work. This view excludes private task
payloads, principal/request records, credentials and source-session keys.

`AMBIGUOUS_BINDING` identifies a selection conflict, rather than runtime
recovery. Existing session affinity takes precedence over endpoint priority;
equal-priority alternatives require an approved selection group. A busy or
unreconciled affinity does not redirect work to an idle executor. Multiple
bindings in a historical/restored catalog still represent one logical agent.
This behavior does not change onboarding's remote-machine replacement policy.

The separate Contextual capacity panel shows up to 20 recent assessments for
the selected agent's workspace/session contexts: observed idle session or opening
capacity, reserved/in-use capacity, waiting, pending release or unknown. It uses
the runtime's actual observations; opening the panel never probes a harness or
creates a reservation. Installation readiness is not interpreted as availability.
Observations expire within their reported lifetime (at most five seconds),
including in a browser whose next request has stalled. Missing/expired data is
unknown, not zero or idle. Changes of owner, capacity revision, configuration,
authorization, credentials or binding invalidate the prior observation. Scope
validation is read-only and does not advance the persisted revision counters.

The operator-only `GET /api/v1/metrics/local/summary` response includes
`broadcast_handoffs`: bounded historical samples of the latest 1,000 attempts and
1,000 broadcast handoffs. It reports recorded attempt/reservation states,
allowlisted reasons, current winner channel and observed claim/execution delay.
Sample sizes and truncation are explicit; these samples are not global backlog
totals or current free-slot counters. Missing latency observations remain null
with count zero, and storage errors return `status=unavailable`. Labels never
contain handoff, agent, executor or session IDs. Agent-scoped nonoperator metrics
do not expose these global aggregates.

The source-tuple campaign covers separate Server/Connector processes, including
normal and abrupt Connector restart with unused reservations. Discovery/native
providers are synthetic in that campaign. The installed tuple and independent
remote-host campaign remain rollout gates.

Remote execution additionally requires negotiated capacity, scoped lease denial
and confirmed session release. A Connector that lacks the complete set remains
ineligible for new automatic work (`CAPACITY_PROTOCOL_UNSUPPORTED`), without
invoking a model to discover availability. Its historical reservations remain
queryable and releasable.

## Recovery and rollback

The Server owns one bounded scheduler. Capacity signals wake it; durable scans
recover missed signals and interrupted attempts. Retries query the original
reservation and operation IDs. Unknown native effects do not authorize a second
execution or a fictitious capacity release.

Connector recovery negotiates `nexus-preopen-refusal-v1` for an opening whose
publication was persisted before Core admission. The replacement owner first
persists the original association and wins a domain-separated journal admission
against any delayed opening. An existing native intent, including an uncertain
one, cannot be overwritten by this refusal. Physical capacity release is checked
separately before reporting the proof through the authenticated recovery channel.

The Server correlates that proof with the original dispatch, session generation
and capacity ticket. It records the receipt, proof and session closure together.
Lost acknowledgments replay the same proof without reopening the harness. A
constructed runtime with no opening or durable session claim does not wait for a
nonexistent native lease after its producers have drained; its publication and
capacity still require the same durable recovery. The original handoff claim is
preserved. Only a confirmed preopening refusal removes that old work's affinity
block; unresolved native work and ordinary business claims retain their guards.

Shutdown stops new scheduling immediately. Native containment proceeds while
the Server retains outstanding scheduler/database/host producers; a timeout in
an HTTP observer does not release those owners. A database reset waits for that
drain, then starts a new owner for the preserved configuration.

To roll back acquisition, restart with the startup setting set to `false`.
Persisted attempts still start a recovery-only scheduler: unused reservations
are reconciled/released and committed work retains its original identity.
Broadcast notices remain available through MCP/manual consumption and do not
become mass model prompts again. Disabling an agent's opt-in also revokes its
automatic work authority; running work is contained through lease revalidation,
with physical release confirmed separately from business completion.

Local automated lifecycle tests use durable stores and synthetic native peers.
The installed tuple and independent remote-host campaign must be qualified
before rollout; these tests are not universal provider/platform qualification.
