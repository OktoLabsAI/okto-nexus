# HST-003 shared contract, version 1

This reconciles the normative section 8.2 with existing Home DTOs. It is a
read-model extension, not a new runtime state machine or authority.

## Negotiation and rollout

The existing `/info` response advertises `home_presentation_versions: [1, 2]`.
The existing App info read supplies the version to the already opt-in operational
Home; no probe/poll per card. Missing capability means version 1. The operational
Home local-storage default and server feature gate remain unchanged; default
rollout is not approved. A harness endpoint without an explicit query keeps
presentation 1, including its historical Needs You invariant. Version 2 uses
`presentation_version=2`; versions are part of revision/cursor binding and client
scope/cache identity. Unsupported/repeated versions fail closed.

All harness envelopes advertise `presentation_versions` and identify
`presentation_version`. Existing `version:1` transport envelope is unchanged.
Other Home endpoint families reject this query. No old consumer receives new
placement semantics implicitly. Unavailability preserves capability/version but
never synthesizes exact empty counts or Idle.

## Operational status

Version 2 harness cards add `operational_status` with the exact enums of section
8.2. Its counters use existing vocabulary `{value:number|null,total_is_exact:boolean}`
instead of a second `exact` spelling. `pending_by_kind` has the four question,
approval, decision and verification counters. `state_since` is null without a
proven transition; `as_of` is evidence time rather than a fabricated activity start.

Cards add `placement_reason`: `normal_monitoring`, `human_block_confirmed`,
`awaiting_native_confirmation` or `monitoring_unconfirmed`. Legacy activity_state
is retained. Awaiting confirmation does not force blocks_harness=true and does
not create an actionable occurrence. Opaque `resume_confirmation_refs` bind the
decision/request, operation, session and epoch to the earlier confirmed block.
Stale/old-epoch receipts cannot discharge that state.

Version 2 request cards add `blocks_session:boolean|null`, an action kind and
the unique canonical occurrence. Shared/unknown ownership stays independent.
All own requests are incorporated into a fully blocked harness exactly once.
Pending request previews are bounded; complete counts precede paging. Additional
requests use `/home/harness-board/cards/{card_id}/requests?presentation_version=2`
with a `harness_requests` envelope and a card/principal/scope/version/revision
bound cursor. Same projection, no new inventory or screen.

The root adds `operational_summary`, with explicit Count objects for connected,
working, idle, queued, unconfirmed, disconnected, blocked_harnesses,
pending_actions, visible_notifications and resume_confirmations. These are
different units and are never summed as Kanban stages. Positive current progress
can survive unrelated incomplete coverage; proving absence/global blocking/Idle
requires complete pertinent coverage. Registered bindings alone never prove
connectivity. One-shot closed sessions remain no_active_session.

## Delivery semantics

`HomeResult.delivery_semantics` and the containing delivery's
`delivery_semantics` refer to the same computed proof object (not independent
statuses). External reports get the same shape with reported evidence.
Fields/enums follow section 8.2, including semantic_revision and historical.
Existing outcome/verification_state fields retain legacy meaning.

The existing handoff verification transition will emit additive metadata tying
the existing pass/fail/request event to the exact verified claim and persisted
delivery revision. Fail records the old verified epoch before any new epoch.
No table, QA workflow or protocol is added. Historical events without that
correlation remain unknown; COMPLETED alone is never approved. Productive turn
closure, handoff completion, verification, cleanup and content availability remain
independent. The same retained result ID survives changes in its semantics.

## Interaction and security

One canonical snapshot, paused visual ordering and exact detail interaction have
independent gates. Identical polls do not create pending updates; normal updates
use notice/status rather than error/alert. Exact reads revalidate their target
without closing the panel. Paging resynchronizes at a new revision; decision
controls still require current authorization/revision/idempotent intent.
Logout/revocation discards protected state immediately, regardless of pause.

Unique-session direct opening requires the complete relation or an explicit
exact target; never latest/session-preview guessing. Multiple sessions keep an
explicit selector with labels/project/state and exact refs. No GET starts a
session, Test, grant, process probe, filesystem artifact read or provider call.

Ownership: Root implements HTTP/service negotiation, App info wiring and frontend
types/validators/API. Operational projection owns batch facts/reduction/board.
Results projection owns SQLite Results/proof events/helper. Interaction owns
controller/detail/panel. Cards integrate only after these contracts exist.
Evidence remains layer/adapter/version scoped; human testing is deferred until
implementation, automated browser checks and installed package are ready.
