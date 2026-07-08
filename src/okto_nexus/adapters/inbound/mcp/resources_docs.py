"""Deep tool-docs + target-grammar MCP resources (Frente 1, card C2).

These resources hold the REFERENCE DEPTH that used to live inline in every
tool's docstring and ``_P_*`` parameter description: full examples, rationale,
enum prose, edge cases, the complete routing-target grammar. The ``tools/list``
surface now carries only a compact one-line summary per tool plus the minimal
per-parameter facts (name/type/required/minimal-enum); an agent reads here on
demand - exactly the Okto Pulse ``okto-pulse://reference/tool-docs/*`` pattern.

DESIGN LOCK (inegociável): only depth moves here. The compact inline surface
must still let an agent call any tool correctly on the FIRST try (verified by
the S7 "harness without resources" gate). The routing-target grammar resource
is referenced by BOTH message_create and handoff_create, eliminating the
~1.000-char duplication of ``_P_TARGET_MSG`` / ``_P_TARGET_HANDOFF``.

Importing this module runs its ``add_resource`` side effects, registering the
target-grammar + the six per-domain tool-docs + the governance and hitl
references into the shared registry in ``resources.py``. ``resources.py``
imports this module at the bottom so a single ``register_resources(server)``
publishes the full closed set (BR9: 12 URIs).
"""

from __future__ import annotations

from .resources import add_resource

# --------------------------------------------------------------------------- #
# Routing target grammar (FR4): the full prose, relocated out of the two tools.
# --------------------------------------------------------------------------- #
add_resource(
    slug="target-grammar",
    name="Routing target grammar",
    description="The full routing-target grammar (every strategy shape, rules, examples, edge cases) shared by message_create and handoff_create.",
    version="4",
    body="""\
# Routing target

Pass ``target`` as a raw JSON OBJECT (dict), e.g. \
``{"strategy":"direct","agent_id":"<id>"}`` - NEVER a JSON-encoded string. The
target selects the recipient set (message_create: who receives it) or the
eligibility set (handoff_create: who may CLAIM it).

## Strategies and shapes

- **direct** - ``{"strategy":"direct","agent_id":"<id>"}``. Reaches that GLOBAL
  agent in any workspace. message_create: unknown agent -> NOT_FOUND.
  handoff_create: the named agent must be REGISTERED (NOT_FOUND otherwise; for
  an agent that will register later use ``direct_with_fallback``).
- **capability** - ``{"strategy":"capability","capability":"<cap>"}``. ``<cap>``
  is a string OR a list (any-of). Global registry; discover with
  ``capability_list``. FAIL-CLOSED: every referenced name must be REGISTERED
  in the operator-managed capability catalog (VALIDATION_ERROR listing the
  unregistered names otherwise) - also enforced on sub-rules inside ``mixed``
  and on a ``direct_with_fallback`` fallback.
- **role** - ``{"strategy":"role","role":"<role>"}``. Exact, case-sensitive;
  global.
- **tag** - ``{"strategy":"tag","selector":<selector>}``. Agents whose
  operator-set tags satisfy the selector (message_create: present matching
  agents; handoff_create: claimable by matching agents). The selector takes
  either form:
  - FLAT map ``{"<key>":["<value>",...]}`` - AND across keys, OR (non-empty
    intersection) within a key's values. Sugar for one ``In`` expression per
    key.
  - RICH match-expression list (Kubernetes parity)
    ``[{"key":"<k>","operator":"In|NotIn|Exists|DoesNotExist","values":[...]}]``
    - expressions are ANDed. ``In``: the agent's values under ``key``
    intersect ``values``. ``NotIn``: no intersection OR the key is absent.
    ``Exists`` / ``DoesNotExist``: bare presence/absence checks - they FORBID
    ``values`` (In/NotIn REQUIRE a non-empty list).
  - ABSENCE TRAP (K8s parity): ``NotIn`` and ``DoesNotExist`` MATCH agents
    that lack the key entirely - a lone ``NotIn`` matches every untagged
    agent. Compose with ``Exists`` on the same key to mean "has the key AND
    is not X".
  - HIERARCHY: values containing ``/`` match by path SEGMENT - selector value
    ``ENG`` covers tags ``ENG`` and ``ENG/BACKEND`` but never ``ENGX``;
    ``NotIn ENG`` excludes the whole ``ENG/*`` subtree. No inheritance across
    different keys.
  - Every referenced key (all operators) and every In/NotIn value must be
    REGISTERED in the operator-managed tag catalog (fail-closed
    VALIDATION_ERROR otherwise); an empty selector is rejected (use a bare
    broadcast).
- **broadcast** - ``{"strategy":"broadcast"}``. message_create: the workspace's
  active-session (heartbeat-fresh) agents. handoff_create: any agent in the
  workspace.
- **mixed** - ``{"strategy":"mixed","rules":[<sub-target>, ...]}``. OR of
  sub-targets. A ``broadcast`` nested in ``mixed`` is rejected
  (VALIDATION_ERROR).
- **direct_with_fallback** (handoff_create ONLY) -
  ``{"strategy":"direct_with_fallback","agent_id":"<id>",``
  ``"fallback_after_seconds":<n>,"fallback":<sub-target, default broadcast>}``.
  The named worker gets first refusal; after the delay it opens to the fallback
  pool. message_create rejects this strategy - use a handoff for timed
  escalation.

## Rules and edge cases

- message_create: omit ``target`` entirely for a broadcast to the workspace's
  present agents. A group target (capability/role/mixed/broadcast) matching
  NOBODY returns ``recipients:[]`` + a ``warning`` (the message is still
  persisted).
- handoff_create: ``target`` is REQUIRED. Pool targets return ``eligible_count``
  and a ``warning`` when 0 agents currently match (the handoff stays OPEN for
  later registrants; ``handoff_cancel`` retracts a mistake).
- ``direct_with_fallback`` and a ``broadcast`` nested in ``mixed`` are rejected
  on message_create (VALIDATION_ERROR).
- A wrong-typed ``target`` (number/boolean/array) returns the canonical
  VALIDATION_ERROR envelope, not an SDK error.""",
)


# --------------------------------------------------------------------------- #
# Per-domain tool-docs (FR3). Each holds the args/returns/examples/enum prose
# for the tools its module owns; the inline tools/list keeps a 1-line summary.
# --------------------------------------------------------------------------- #
add_resource(
    slug="tool-docs/messages",
    name="Tool docs - messages & channels",
    description="Full reference for message_create / channel_create / channel_list and the migrated message_get/list/wait shims.",
    version="1",
    body="""\
# message_create
Persist a message and emit ``message.created`` in one transaction. The response
IS your delivery confirmation: ``recipients`` names exactly who received it in
their inbox (the fan-out commits atomically with the send) and
``delivered_count`` totals it. Track what happens next with
``message_status(message_id)`` (per-recipient lanes unread/delivered/read/parked)
or wait for the sender-only receipt events ``message.delivered`` / ``message.read``
via event_wait. A broadcast (no target) reaches the workspace's PRESENT agents
only; agents excluded for heartbeat staleness are reported in ``excluded_stale``
+ ``warning``. In trust_mode=strict pass from_session_id + session_secret (from
session_open). For large content, attach an artifact and keep ``body`` a short
pointer. ``target``: see okto-nexus://reference/target-grammar.

# channel_create
Create a channel by name (idempotent). Channels are organizational LABELS, not
ACLs: any agent in the workspace may read/post to any channel; the channel does
NOT decide who receives a message - the message target does. Returns the channel
plus ``created`` (false if the name already existed). Trimmed; max 64 chars;
unique per workspace.

# channel_list
Return the workspace channels (``general`` is seeded by default).

# message_get / message_list / message_wait (MIGRATED, S3)
Replaced by the inbox surface. message_get -> inbox_pull / inbox_peek /
inbox_history. message_list -> inbox_peek / inbox_history (your messages) or
event_get (bus traffic). message_wait -> inbox_count polling or event_wait. The
shims return ``{ok:false,error:{code:"MIGRATED"}}`` naming the exact replacement;
they are kept so a pre-S3 client gets prescriptive guidance instead of an opaque
"unknown tool".""",
)

add_resource(
    slug="tool-docs/inbox",
    name="Tool docs - inbox",
    description="Full reference for the per-recipient inbox tools (pull/ack/extend/peek/count/history/message_status).",
    version="1",
    body="""\
The inbox is GLOBAL (keyed by agent_id): a direct message reaches you regardless
of which workspace it was sent in. At-least-once: pulled messages are leased; if
you do not ack them before the lease elapses they are redelivered; a message
redelivered too many times is parked (dead-letter).

# inbox_pull
Take your unread messages (and your own lease-expired redeliveries) into
in-flight and return them WITH their body. Index-free: the server tracks your
per-recipient read state, so you never pass a cursor. Size the lease with
``lease_seconds`` (default 120, clamped 10..3600) or renew with inbox_extend.
Pulling emits a ``message.delivered`` receipt to each message's sender. In
trust_mode=strict pass session_id + session_secret.

# inbox_ack
Acknowledge messages into history (read). Returns ``{acknowledged, read_message_ids}``
- the ids that ACTUALLY transitioned. Each transitioned message emits a
``message.read`` receipt to its sender; unless the operator opted out
(inbox_read_receipts) the sender also gets a compact ``message.read_receipt``
notification in its own inbox. Receipts never generate receipts.

# inbox_extend
Renew the lease on in-flight messages you pulled but have not finished. New
lease = now + extend_seconds (clamped 10..3600). All-or-nothing: if any id is not
in-flight the call fails with a per-message reason and nothing is extended.

# inbox_peek
READ-ONLY triage of pending (unread + in-flight) WITHOUT consuming. Envelope-only
by default: ``body_preview`` (first 200 chars) + ``body_bytes`` instead of the
full body. ``include_parked=true`` also shows dead-lettered messages;
``include_bodies=true`` opts into full bodies.

# inbox_count
READ-ONLY lane sizes ``{unread, in_flight, read}``. Cheap between-turns check;
an elapsed in-flight lease is counted as ``unread``. Parked excluded.

# inbox_history
List acknowledged (read) messages, newest-first, keyset-paginated (stable pages
even while you keep acknowledging).

# message_status
Track a message you SENT: ``{message_id, deliveries, count}`` where each delivery
is ``{recipient, status, attempts, read_at}`` and status is
unread/delivered/read/parked. Use it instead of re-sending when a recipient
seems silent.""",
)

add_resource(
    slug="tool-docs/events",
    name="Tool docs - event log",
    description="Full reference for event_get / event_cursor / event_wait (streams, filters, cursors, the long-poll).",
    version="1",
    body="""\
Events are OBSERVABILITY (audit/monitoring of message.created, handoff.*,
session.* events); they are NOT how you receive messages addressed to you - that
is the inbox. stream is one of: workspace, agent, handoff. message.created, the
sender-only receipts message.delivered/message.read and artifact.created are on
``workspace``. filters (equality, AND-combined) allow keys: type, agent_id,
task_id, handoff_id. Visibility is per-event: you only see events you may see.

# event_get
Read a cursor-paginated page (non-blocking). cursor = the last event_id you
consumed (returns event_id > cursor; omit/0 = from the beginning). limit default
100, clamped to the server max (default 1000). Returns
``{events, next_cursor, has_more, timed_out:false}``.

# event_cursor
Return the stream's CURRENT END as a cursor in O(1) (no scan). The pre-flight
monitor anchor: call once at startup and feed the cursor into your
event_get/event_wait loop so you see only events appended AFTER this moment.
Returns ``{cursor}`` (0 for an empty stream).

# event_wait
Snapshot by default (``timeout_seconds`` omitted/0/null = a single non-blocking
scan). ``timeout_seconds > 0`` OPTS IN to a blocking long-poll: it parks until a
matching event arrives or the timeout elapses (clamped to the server ceiling),
then returns the page; loop on next_cursor. This IS the listener surface - call
it on this MCP connection; never `okto-nexus tail`. See
okto-nexus://reference/monitoring for the listener patterns.""",
)

add_resource(
    slug="tool-docs/handoff",
    name="Tool docs - handoff",
    description="Full reference for the handoff lifecycle (create/list_available/claim/complete/verify/reject/cancel/get), including the opt-in VERIFYING cycle and DAG dependencies.",
    version="3",
    body="""\
Competing-consumers: every eligible agent SEES a handoff but only the first to
handoff_claim wins (others get HANDOFF_ALREADY_CLAIMED); an unfinished claim's
lease expires and the work returns to the pool. visibility (who may SEE) is
separate from target (who may CLAIM): one of public / eligible / private.
``payload`` is the inline work content, returned only to the agent that wins
handoff_claim (and later to that same claimant via handoff_get). Discovery,
events and directed inbox notifications stay metadata-only. For ``target`` see
okto-nexus://reference/target-grammar.

Verification-first (opt-in per handoff, needs the feature_verification flag):
creating with ``acceptance_criteria`` adds a VERIFYING stage between the
claimant's delivery and COMPLETED - handoff_complete parks the handoff in
VERIFYING and the ``verify_by`` verifier decides via handoff_verify ('pass' ->
COMPLETED, 'fail' -> back to CLAIMED for rework with feedback + renewed lease).
While the flag is OFF the params are REJECTED (a verification contract is
never accepted-and-ignored); without them nothing changes.

Dependencies / DAG (opt-in per handoff, needs the feature_dag flag): creating
with ``depends_on`` (1..20 unique ids of EXISTING same-workspace handoffs;
IMMUTABLE, so cycles are impossible by construction) makes the handoff a
BLOCKED dependent: it stays OPEN but is excluded from handoff_list_available
and refused at claim (DEPENDENCY_NOT_MET) until EVERY dependency is
COMPLETED - VERIFYING does not satisfy, only the verified/plain COMPLETED
does. When the LAST dependency completes the bus emits ``handoff.unblocked``
({handoff_id: the dependent, unblocked_by}) in the same transaction and
notifies a direct dependent's named agent by inbox - claim then proceeds
normally. If a dependency is REJECTED or CANCELLED the dependent can never
unblock: the bus emits ``handoff.dependency_failed`` and notifies the
dependent's CREATOR, who decides (cancel the dependent, or re-create the
work - edges never reattach). There is NO cascade. While the flag is OFF the
param is REJECTED (never accepted-and-ignored); flipping the flag OFF later
keeps existing dependents fully decidable (the gates read the stored edges,
not the flag).

# handoff_create
Create an OPEN handoff; emit handoff.created. A direct target must name a
REGISTERED agent (the named agent gets a metadata-only inbox notification -
``notified`` in
the response). Pool targets return ``eligible_count`` + a ``warning`` when 0
match (stays OPEN for later registrants). After creating, poll handoff_get for
status/result - do not scan the event stream. payload: a string is returned to
the claimant byte-for-byte; a non-string is stored/returned to the claimant as
opaque JSON TEXT.
Optional verification contract: ``acceptance_criteria`` (1..20 non-empty
strings, max 500 chars each, no exact duplicates, IMMUTABLE after creation) +
``verify_by`` (one of {"kind":"creator"} - the default, materialised at
creation; {"kind":"agent","agent_id":...} - must be registered;
{"kind":"capability","capability":...} - must be in the catalog, resolved
dynamically at verify time). verify_by without acceptance_criteria is
rejected, as is a contract only the claimant could ever verify.
Optional ``depends_on`` (feature_dag): every id must name an EXISTING handoff
in this workspace - unknown ids fail with DEPENDENCY_NOT_FOUND (details
``{missing: [ids]}``; a cross-workspace id reads as nonexistent), and an
already-REJECTED/CANCELLED dependency makes the create statically
unsatisfiable (VALIDATION_ERROR) - drop it or re-create the work first. An
already-COMPLETED dependency is born satisfied. The response echoes
``depends_on`` plus a ``dependencies`` aggregate {total, satisfied, pending,
failed}; a directed dependent born blocked gets the "(blocked)" suffix on its
inbox notification subject.

# handoff_list_available
Expire leases, then list OPEN handoffs visible+eligible to the caller
(paginated). Entries are metadata-only and do not include ``payload``; the
payload is revealed only after a successful claim. ``timeout_seconds > 0`` opts
into a blocking long-poll until a claimable handoff appears.

# handoff_claim
Atomically claim an OPEN handoff; single winner, others get a structured error.
Returns the ``payload`` plus ``claimed_by`` / ``lease_expires_at``. strict mode:
session_id + session_secret. A BLOCKED dependent is refused with
DEPENDENCY_NOT_MET (details carry aggregate ``{handoff_id, pending, failed}``
counts only - dependency ids are never disclosed): wait for its
``handoff.unblocked`` event (or the "unblocked" inbox notice on a directed
handoff), then claim again. ``failed > 0`` means it can NEVER unblock - the
creator must decide.

# handoff_complete
Owner-only delivery of a CLAIMED handoff. Without acceptance_criteria:
-> COMPLETED, emit handoff.completed, result delivered to the creator's inbox
(exactly as always). With acceptance_criteria: -> VERIFYING, emit
handoff.verification_requested (metadata-only: the contract, never the
result) and notify a statically resolvable verifier; the outcome then belongs
to handoff_verify. strict mode: session credentials.

# handoff_verify
Verifier-only verdict on a VERIFYING handoff. The verifier is resolved from
``verify_by`` AT VERIFY TIME (creator -> the creator; agent -> that exact
agent; capability -> any agent currently announcing it); the claimant can
NEVER verify their own delivery, eligible or not. 'pass' -> COMPLETED,
emitting the CANONICAL handoff.completed enriched with ``verified_by`` (there
is no separate passed event) and notifying the creator. 'fail' -> CLAIMED for
rework: ``feedback`` (optional, max 2000 chars, only with 'fail') is persisted
(each fail overwrites the previous; history lives in the event log), the
claimant's lease is RENEWED and handoff.verification_failed is emitted +
delivered to the claimant's inbox. VERIFYING is protected: reject/cancel
refuse it and lease expiry never touches it. strict mode: session credentials.

# handoff_reject
Reject a handoff (owner CLAIMED->REJECTED or direct-target OPEN->REJECTED).
``reason`` is persisted + delivered to the creator's inbox. A VERIFYING
handoff cannot be rejected - only a 'fail' verdict returns it to CLAIMED.

# handoff_cancel
Creator-only OPEN -> CANCELLED; retract a handoff nobody should take (e.g. a
pool target that matched zero agents). Only OPEN handoffs cancel.

# handoff_get
Read one handoff by id: status, claimant, result/rejected_reason; ``payload``
is included only when the reader is the claimant. THIS is the creator's path to
the outcome after handoff_create (do not scan events).
An expired claim lease reads as OPEN again. Verification-first handoffs also
expose ``acceptance_criteria``/``verify_by`` (decoded) and
``verification_feedback`` - each omitted when NULL. Dependent handoffs expose
``depends_on`` plus the LIVE ``dependencies`` aggregate {total, satisfied,
pending, failed} (derived on-read); both omitted on a dependency-free
handoff.""",
)

add_resource(
    slug="tool-docs/identity",
    name="Tool docs - identity & sessions",
    description="Full reference for workspace/agent/session tools (resolve, whoami, register, list, get, capability_list, session open/heartbeat/close, workspace_list).",
    version="3",
    body="""\
Agents are GLOBAL identities; workspaces are per-project. workspace_list /
agent_list / agent_get / capability_list are deliberately cross-workspace
(discovery); everything else is workspace-scoped.

# workspace_resolve
Resolve project_root to its deterministic workspace_id = sha256(realpath) and
upsert it.

# agent_whoami
Return YOUR OWN profile, derived from your API key (no parameters): agent_id,
operator-assigned role, capabilities, metadata, permissions (null = unrestricted).
The recommended FIRST call. VALIDATION_ERROR on a connection with no
authenticated identity (open cooperative stdio): there, read profiles with
agent_get.

# agent_register
Update YOUR OWN identity profile (role/capabilities/metadata). SELF-ONLY on an
authenticated connection: your key already names your identity; registering a
new identity or touching another agent's profile returns PERMISSION_DENIED.
Self-updates are permission-gated: role/metadata/capability changes require
``identity.update_profile`` and capability changes also require
``identity.update_capabilities``.
capabilities accepts a flag-map ({"ocr":true}), a list (["ocr","pdf"]), or a
single name. Capability names are FAIL-CLOSED against the central capability
catalog: every announced name must already be registered by an operator
(dashboard Registry or POST /api/v1/capabilities), or the write is rejected
with VALIDATION_ERROR listing the unregistered names. Discover the sanctioned
vocabulary with capability_list; agents never define new names themselves.

# agent_list / agent_get
List all registered agents (global), each with role/capabilities and
last_seen_at; or read one agent's details. Discovery surface for addressing.

# capability_list
List the central capability catalog merged with ownership: EVERY registered
name appears (with its description), including names nobody advertises yet
(agent_count 0). Per name, the agents that possess it - normalised exactly as
capability routing matches. Use it to pick a valid name BEFORE agent_register
or a {"strategy":"capability"} target: unregistered names are rejected
fail-closed on every write path.

# session_open
Open a session bound to (agent_id, workspace_id); the server assigns the id and
returns a per-session ``session_secret`` (ONLY here - keep it). In
trust_mode=strict the sensitive verbs require session_id + session_secret.
On an authenticated connection, session_open is self-only: the API-key identity
must match the requested agent_id.
Only heartbeat-fresh sessions receive broadcasts and read PRESENT - but you do
NOT have to spam session_heartbeat: any AUTHENTICATED active verb (pass your
session_id + session_secret) advances the heartbeat for you, so receiving
(inbox_pull), sending and claiming keep you present while you work. Use
session_heartbeat explicitly only when you are idle but want to stay present.

# session_heartbeat
Advance a session heartbeat and report the derived status; keeps you PRESENT and
clear of the stale-session reaper. Note: any authenticated active verb already
advances your heartbeat, so reserve explicit heartbeats for IDLE stretches (e.g.
while parked on an event_wait long-poll) where you take no other action.

# session_close
Close a session (idempotent).

# poll_token_issue / poll_token_renew / poll_token_revoke
Control-plane helpers for remote monitors. ``poll_token_issue(session_id,
session_secret)`` returns a raw ``nxsept_`` bearer exactly once, bound by the
server to this authenticated agent, this session and this workspace. Give that
bearer only to a background process that calls the read-only data plane:
``GET /api/v1/events/cursor``, ``GET /api/v1/events``,
``GET /api/v1/inbox/count`` and ``GET /api/v1/inbox/peek``. The token cannot
call MCP or mutate state, has a short TTL, is stored only as a hash, and must be
renewed before ``expires_at`` or revoked on teardown. See
okto-nexus://reference/monitoring for the full remote-poller loop.

# workspace_list
GLOBAL-ADMIN: enumerate ALL workspaces. By default paths are OMITTED
(workspace_id, display_name, created_at, last_seen_at); pass include_paths=true
only for an explicit admin/ops need (disclosing every project's on-disk layout is
opt-in defense-in-depth). When an actor is known, workspace_list requires
``workspaces.list`` and include_paths additionally requires
``workspaces.include_paths``.""",
)

add_resource(
    slug="tool-docs/artifacts",
    name="Tool docs - artifacts",
    description="Full reference for artifact_put / artifact_get.",
    version="1",
    body="""\
# artifact_put
Register a file/text/json/markdown artifact in the resolved workspace. Provide
``path`` (register by REFERENCE - must stay within the workspace root; only the
path + metadata are stored, never the bytes) OR ``content`` (inline UTF-8,
bounded by max_inline_bytes; json must be well-formed) - at least one is
REQUIRED. ``artifact_type`` one of: file, text, json, markdown (the type is a
label; inline-vs-reference is decided by content-vs-path). Emits
``artifact.created``.

# artifact_get
Retrieve an artifact by id within the workspace resolved from project_root.""",
)

# --------------------------------------------------------------------------- #
# Governance reference (spec ffef15bf, feature_governance - surface rev 19).
# --------------------------------------------------------------------------- #
add_resource(
    slug="governance",
    name="Governance policies",
    description="Operator-set deny rules and quotas: subject model, actions, limit kinds, deny-overrides semantics, windows, and the POLICY_DENIED / QUOTA_EXCEEDED error format.",
    version="1",
    body="""\
# GOVERNANCE POLICIES (feature_governance, default OFF)

Operators can set GLOBAL policies that the bus enforces BEFORE persisting a
write. When the flag is OFF nothing is enforced and nothing changes for you.
When it is ON, a write that violates a policy fails with a normative error -
your request is NOT persisted and recipients never see it.

## Subject model - who a policy matches
Each policy names ONE subject: a specific ``agent`` (your agent_id), a ``role``
(your operator-assigned role, exact match), a ``capability`` (any agent
advertising that catalog capability), or ``star`` (every agent, including
callers with no identity). Policies are GLOBAL - not per-workspace - and your
consumption is counted across ALL workspaces.

## Actions - what a policy covers
One of: ``message_create``, ``broadcast``, ``handoff_create``, ``artifact_put``.
``broadcast`` is the explicit {"strategy":"broadcast"} target AND the
target-less, channel-less send (same reach). A ``message_create`` policy also
covers broadcast (broadcast IS a message create); a ``broadcast`` policy does
NOT restrict direct/targeted sends.

## Limit kinds - what a policy does
* ``deny`` - the action is categorically blocked for the subject.
* ``max_count`` - at most N actions per rolling window (``1h`` or ``24h``),
  counted per agent across all workspaces, evaluated pre-write (the attempt
  that would exceed the limit fails; completed ones stay).
* ``max_bytes`` - the payload/body/content may not EXCEED N bytes (exactly N
  passes; N+1 fails). Applies to the UTF-8 byte size of the message body,
  handoff payload, or artifact content.
* ``max_open_handoffs`` - at most N of your created handoffs may be
  non-terminal at once; completing/cancelling/rejecting one frees the slot.

## Evaluation semantics
Deny-overrides: if ANY applicable deny matches, it wins over every quota.
Otherwise quotas are checked in deterministic order (created_at, then
policy_id) and the first violation is reported. Disabled policies are ignored.
No applicable policy = allowed.

## Errors you can receive
* ``POLICY_DENIED`` (HTTP 403) - a deny matched. details: {policy_id, action,
  limit_kind}.
* ``QUOTA_EXCEEDED`` (HTTP 429) - a quota matched. details: {policy_id, action,
  limit_kind, limit, window?, current?}.
Both are terminal for that attempt - do NOT retry a deny; for quotas, wait for
the window to roll or reduce your payload. The details only ever describe YOUR
own matched policy - never other agents' state. Every denial is also audited
as a ``governance.denied`` event on the workspace stream (payload carries the
policy/action context, never your subject/body).

## Discovering the policies that apply to YOU
``agent_whoami`` includes a ``governance`` block - a list of {policy_id,
action, limit_kind, limit?, window?} - ONLY when the flag is ON and at least
one active policy matches you. No block = nothing restricts you right now.
Policies are managed by operators over REST (/api/v1/governance/policies) and
the dashboard; agents cannot create or edit them.""",
)


# --------------------------------------------------------------------------- #
# HITL approvals reference (spec 2948b2a2, feature_hitl - surface rev 20).
# --------------------------------------------------------------------------- #
add_resource(
    slug="hitl",
    name="Human-in-the-loop approvals",
    description="What a pending_approval envelope means, which approval.* events to watch via event_wait, how a rejection reaches you, and why you must never re-send while pending.",
    version="1",
    body="""\
# HITL APPROVALS (feature_hitl, default OFF)

Operators can require HUMAN APPROVAL for specific actions by setting a
governance policy with limit_kind ``require_approval``. Interception only
happens when BOTH ``feature_governance`` and ``feature_hitl`` are ON; with
either flag OFF nothing changes for you. When it triggers, your write is NOT
executed: it is parked as a pending approval for a human operator to decide.

## The pending envelope
An intercepted ``message_create`` / ``handoff_create`` (broadcast included)
still returns ``ok: true`` - branch on ``data.status``:

    {"status": "pending_approval", "approval_id": "apr_...",
     "action": "message_create", "policy_id": "pol_...",
     "watch": {"stream": "workspace",
               "types": ["approval.granted", "approval.denied"],
               "approval_id": "apr_..."},
     "trace_id": "..."}   # present only when tracing resolved one

Nothing was delivered and no recipient saw anything. Your ORIGINAL arguments
are stored server-side and will be executed VERBATIM if approved - there is
nothing for you to re-send.

## While it is pending
* Do NOT retry or re-send the action. A retry is intercepted again and files
  a SECOND pending approval: it will not go out faster, and the operator now
  has duplicates to reject. One request = one approval_id = one decision.
* WAIT using the ``watch`` block: ``event_wait(stream="workspace",
  filters={"type":"approval.granted"})`` (and/or ``approval.denied``), keeping
  only events whose ``approval_id`` matches yours - it is surfaced on every
  projection profile.
* You are not blocked: keep doing other work; only this one action is parked.

## Outcomes
* ``approval.granted`` - an operator approved and the bus ALREADY EXECUTED
  your original request (same arguments, same side effects, receipts and
  events as a normal call). Do not re-send.
* ``approval.denied`` - the action was rejected and will NEVER execute. The
  operator's justification arrives as a DIRECT message in your inbox from
  agent ``operator`` (subject ``Approval <id>: <action> rejected``).
  inbox_ack it, adapt to the feedback, and only then submit a NEW request if
  still needed.

## Semantics and guarantees
* approval.* event payloads carry METADATA ONLY ({approval_id, action,
  agent_id, policy_id, decided_by, trace_id?}) - never your subject/body.
* Decisions are OPERATOR-ONLY (dashboard / REST); agents cannot approve or
  reject - not even their own requests. The FIRST decision is final (a second
  one gets CONFLICT); there is no un-approve.
* Precedence: a matching ``deny`` still returns POLICY_DENIED and quotas are
  still checked FIRST - interception only replaces an action that would
  otherwise have PASSED.
* ``agent_whoami``'s ``governance`` block lists any ``require_approval``
  policy matching you, so you can anticipate the interception before
  writing.""",
)
