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
target-grammar + the six per-domain tool-docs into the shared registry in
``resources.py``. ``resources.py`` imports this module at the bottom so a single
``register_resources(server)`` publishes the full closed set (BR9: 10 URIs).
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
    version="1",
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
  ``capability_list``.
- **role** - ``{"strategy":"role","role":"<role>"}``. Exact, case-sensitive;
  global.
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
    description="Full reference for the handoff lifecycle (create/list_available/claim/complete/reject/cancel/get).",
    version="1",
    body="""\
Competing-consumers: every eligible agent SEES a handoff but only the first to
handoff_claim wins (others get HANDOFF_ALREADY_CLAIMED); an unfinished claim's
lease expires and the work returns to the pool. visibility (who may SEE) is
separate from target (who may CLAIM): one of public / eligible / private.
``payload`` is the inline work content, returned by handoff_list_available and
handoff_claim so the worker need not correlate the event. For ``target`` see
okto-nexus://reference/target-grammar.

# handoff_create
Create an OPEN handoff; emit handoff.created. A direct target must name a
REGISTERED agent (the named agent gets an inbox notification - ``notified`` in
the response). Pool targets return ``eligible_count`` + a ``warning`` when 0
match (stays OPEN for later registrants). After creating, poll handoff_get for
status/result - do not scan the event stream. payload: a string is returned
byte-for-byte; a non-string is stored/returned as opaque JSON TEXT.

# handoff_list_available
Expire leases, then list OPEN handoffs visible+eligible to the caller
(paginated). Each entry includes the ``payload`` so a worker can triage before
claiming. ``timeout_seconds > 0`` opts into a blocking long-poll until a
claimable handoff appears.

# handoff_claim
Atomically claim an OPEN handoff; single winner, others get a structured error.
Returns the ``payload`` plus ``claimed_by`` / ``lease_expires_at``. strict mode:
session_id + session_secret.

# handoff_complete
Owner-only CLAIMED -> COMPLETED; emit handoff.completed; result delivered to the
creator's inbox. strict mode: session credentials.

# handoff_reject
Reject a handoff (owner CLAIMED->REJECTED or direct-target OPEN->REJECTED).
``reason`` is persisted + delivered to the creator's inbox.

# handoff_cancel
Creator-only OPEN -> CANCELLED; retract a handoff nobody should take (e.g. a
pool target that matched zero agents). Only OPEN handoffs cancel.

# handoff_get
Read one handoff by id: status, claimant, payload, result/rejected_reason. THIS
is the creator's path to the outcome after handoff_create (do not scan events).
An expired claim lease reads as OPEN again.""",
)

add_resource(
    slug="tool-docs/identity",
    name="Tool docs - identity & sessions",
    description="Full reference for workspace/agent/session tools (resolve, whoami, register, list, get, capability_list, session open/heartbeat/close, workspace_list).",
    version="1",
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
capabilities accepts a flag-map ({"ocr":true}), a list (["ocr","pdf"]), or a
single name.

# agent_list / agent_get
List all registered agents (global), each with role/capabilities and
last_seen_at; or read one agent's details. Discovery surface for addressing.

# capability_list
List the capabilities advertised across all agents, each with the agents that
possess it - normalised exactly as capability routing matches.

# session_open
Open a session bound to (agent_id, workspace_id); the server assigns the id and
returns a per-session ``session_secret`` (ONLY here - keep it). In
trust_mode=strict the sensitive verbs require session_id + session_secret.
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

# workspace_list
GLOBAL-ADMIN: enumerate ALL workspaces. By default paths are OMITTED
(workspace_id, display_name, created_at, last_seen_at); pass include_paths=true
only for an explicit admin/ops need (disclosing every project's on-disk layout is
opt-in defense-in-depth).""",
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
