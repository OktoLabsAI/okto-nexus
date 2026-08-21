"""MCP resources: on-demand reference docs (Frente 1 - residente).

The MCP ``instructions`` block and the per-tool descriptions are RESIDENT in
every agent's context window on every turn. To cut that fixed cost without
hurting first-try tool-call correctness (the owner's lock: *assertividade de
uso > economia de tokens*), the DEEP reference material lives here, behind
``resources/read``, and is pulled ON DEMAND - mirroring how Okto Pulse serves
``okto-pulse://reference/*``.

DESIGN LOCK (inegociável): only REFERENCE DEPTH moves here - extended examples,
rationale/defense-in-depth, full enum prose, anti-patterns, the monitoring
narrative, receipt mechanics. The minimum needed to call a tool correctly on
the first attempt (per-parameter name+type+required+minimal-enum, the one-line
"what it does", behaviour-changing defaults, the 4-step pre-flight summary)
STAYS inline. Each resource declares a ``version:`` frontmatter so a client can
detect a stale cache (``nexus_info`` reports the set; bump on every change).

This module is part of the INBOUND MCP adapter only; it never touches
domain/application (hexagonal). C1 seeds the instruction-prose resources
(communication / monitoring / preflight) and the registry; C2 adds the
``tool-docs/<domain>`` and ``target-grammar`` resources by calling
:func:`add_resource`.
"""

from __future__ import annotations

from typing import Any

#: URI prefix for every Nexus reference resource.
URI_PREFIX = "okto-nexus://reference/"


def _frontmatter(version: str, body: str) -> str:
    """Prepend a minimal ``version`` frontmatter block to a resource body."""
    return f'---\nversion: "{version}"\n---\n\n{body.strip()}\n'


#: Registry of reference resources: uri -> metadata + body. C2 extends this via
#: :func:`add_resource`. ``version`` is per-resource (bump on content change);
#: ``nexus_info`` surfaces the {uri: version} map for stale-cache detection.
_RESOURCES: dict[str, dict[str, str]] = {}


def add_resource(
    *,
    slug: str,
    name: str,
    description: str,
    version: str,
    body: str,
    mime_type: str = "text/markdown",
) -> str:
    """Register a reference resource under ``okto-nexus://reference/<slug>``.

    Returns the full URI. Idempotent by URI (re-registering overwrites). The
    body is wrapped with a ``version`` frontmatter so every resource is
    self-describing and cache-detectable.
    """
    uri = f"{URI_PREFIX}{slug}"
    _RESOURCES[uri] = {
        "name": name,
        "description": description,
        "version": version,
        "mime_type": mime_type,
        "body": _frontmatter(version, body),
    }
    return uri


def resource_versions() -> dict[str, str]:
    """Return the ``{uri: version}`` map (consumed by ``nexus_info``)."""
    return {uri: meta["version"] for uri, meta in sorted(_RESOURCES.items())}


def resource_uris() -> list[str]:
    """Return the sorted list of registered resource URIs (BR9: closed set)."""
    return sorted(_RESOURCES)


def register_resources(server: Any) -> list[str]:
    """Register every entry in :data:`_RESOURCES` on the FastMCP ``server``.

    Uses ``server.add_resource`` via a tiny FunctionResource so the body is
    served verbatim on ``resources/read``. Returns the URIs registered. The SDK
    is imported lazily here (only when a live server is wired) so importing this
    module never requires the MCP SDK.
    """
    from mcp.server.fastmcp.resources import FunctionResource
    from pydantic import AnyUrl

    registered: list[str] = []
    for uri, meta in _RESOURCES.items():
        body = meta["body"]

        def _read(_body: str = body) -> str:
            return _body

        server.add_resource(
            FunctionResource(
                uri=AnyUrl(uri),
                name=meta["name"],
                description=meta["description"],
                mime_type=meta["mime_type"],
                fn=_read,
            )
        )
        registered.append(uri)
    return registered


# --------------------------------------------------------------------------- #
# C1 seed resources: the long prose relocated out of SERVER_INSTRUCTIONS.
# The inline instructions keep only the actionable pre-flight + pointers here.
# --------------------------------------------------------------------------- #

add_resource(
    slug="preflight",
    name="Pre-flight (full)",
    description="The exact first-turn bootstrap sequence, in full detail.",
    version="4",
    body="""\
# PRE-FLIGHT - run this EXACT sequence on your FIRST turn, in order, BEFORE \
starting whatever the user asked. It is cheap and idempotent; every agent \
bootstrapping the same way is what makes the swarm predictable.

1. IDENTITY - agent_whoami(): your agent_id, operator-assigned role, \
capabilities, permissions and resolved ``communication`` style when one is \
bound. Use that agent_id everywhere. Treat ``role`` and \
``communication.content`` as your DEFAULT OPERATING CONTRACT: role guides your \
responsibilities, operating perspective and decision boundaries; communication \
content guides tone, format, language, verbosity, structure and additional \
instructions in user-facing and agent-to-agent communication. Apply both unless \
the user explicitly directs otherwise for the current task or interaction. A \
user override is task-scoped: it does not modify the Nexus profile and never \
grants permissions or bypasses governance, policies, guardrails, approvals, \
communication scope, safety rules, or higher-priority host instructions. \
Capabilities are routing claims, not authorization or persona. Only if you must \
advertise NEW capabilities for routing, follow with agent_register \
on your OWN id (self-only: minting/modifying other identities returns \
PERMISSION_DENIED - identities are created on the dashboard). Self profile \
updates require identity.update_profile; changing capabilities also requires \
identity.update_capabilities.

2. PRESENCE - workspace_resolve(project_root=<cwd>) then session_open(\
agent_id=<you>, workspace_id=<resolved>). Without an open, heartbeat-fresh \
session you are NOT in the broadcast audience (messages to "everyone" silently \
skip you). Store the returned session_secret and pass session_id + \
session_secret on the verbs that accept them (message_create - named \
from_session_id there; handoff claim/complete/verify/reject/cancel; inbox \
pull/ack/extend; poll_token_*): each validated call advances your heartbeat, \
so working keeps you present. Read-only verbs (event_*, inbox count/peek, \
discovery) do NOT advance it - call session_heartbeat on idle or read-only \
stretches. On authenticated connections, session_open is self-only: use \
exactly your agent_whoami agent_id. Presence/heartbeat depth: \
okto-nexus://reference/tool-docs/identity.

3. BACKLOG - inbox_count(agent_id=<you>); if unread > 0 (an expired in-flight \
lease already counts as unread), inbox_pull and triage what accumulated while \
you were offline (redeliveries included), then inbox_ack what you handled. \
Never skip this: senders are already tracking these deliveries.

4. MONITOR - anchor first: event_cursor(project_root=<cwd>, agent_id=<you>, \
stream="workspace") returns the log's current end, so you only ever see events \
from NOW on. Then use the monitoring mode your harness actually supports: \
background event_wait (timeout_seconds>0) on THIS MCP connection; an EPT \
remote poller (poll_token_issue -> /api/v1/events) when a background process \
can wake the harness; or snapshot polling with event_get between turns. Always \
advance the cursor.

THEN follow the user's instructions. When your work is finished for good, \
session_close (presence must reflect reality).""",
)

add_resource(
    slug="communication",
    name="Communication & inbox",
    description="Intent-based choice among handoff, broadcast message and direct message, plus channels, inbox reception and delivery/read receipts.",
    version="3",
    body="""\
# HOW TO COMMUNICATE - CHOOSE BY INTENT

DECISION RULE: if another agent is expected to PERFORM WORK or produce a \
DELIVERABLE, create a handoff. If the recipient only needs to KNOW something \
or REPLY, use a message and choose direct vs broadcast by audience.

1) HANDOFF - ALL EXECUTABLE WORK. Any request asking another agent to execute, \
investigate, change, build, test, review, validate, or otherwise produce a \
deliverable MUST use handoff_create; message_create must never be the sole \
record of that delegation. Use target={"strategy":"direct","agent_id":"<id>"} \
when the intended assignee is known; that agent still calls handoff_claim to \
accept ownership. Use capability/role/tag/mixed/broadcast/direct_with_fallback \
when the first eligible claimant should own the work. Every handoff has one \
claimant at a time and gives agents and users the canonical, trackable record of \
ownership, status and result. Put the objective, context, scope, constraints and \
expected deliverable in ``payload``; use acceptance_criteria, depends_on and \
verify_by when applicable AND their corresponding feature flags are enabled \
(feature_verification / feature_dag; these fields are rejected while OFF). If N \
agents must execute independently, create N handoffs rather than one \
broadcast-target handoff.

2) BROADCAST MESSAGE - SHARED ALIGNMENT AND INFORMATION. Use message_create \
with target={"strategy":"broadcast"}, or intentionally omit target, to \
disseminate shared context, decisions, announcements, discoveries, risk/blocker \
alerts and general alignment to every PRESENT, reachable recipient selected by \
the workspace and communication scope. Check the response's ``recipients`` to \
see who was actually reached. A broadcast message INFORMS; it does not assign \
work and creates no task owner, claim, lease, status or result. If anyone is \
expected to act, create one or more handoffs.

3) DIRECT MESSAGE - CONVERSATION AND INFORMAL COORDINATION. Use message_create \
with target={"strategy":"direct","agent_id":"<recipient>"} for status checks, \
questions, clarifications, acknowledgements, focused context exchange and \
informal coordination. Reply directly when the answer belongs to that \
conversation. handoff_get is the canonical lifecycle/status/result record; a \
direct message is appropriate when you need contextual progress or blocker \
detail. It may discuss an existing handoff, but it must not be the only record \
of NEW executable work. If conversation creates new work, create a handoff; if \
the work is already in scope, reference the existing handoff_id.

DO NOT CONFUSE THE TWO BROADCASTS. A broadcast MESSAGE is informational fan-out \
to many recipients. A handoff with target={"strategy":"broadcast"} is a CLAIM \
POOL: every eligible agent may see it, but only the first successful \
handoff_claim becomes its ONE executor (others get \
HANDOFF_ALREADY_CLAIMED). An unfinished claim's lease eventually returns the \
work to the pool; it never asks every eligible agent to execute.

CHANNELS are lightweight ORGANIZATIONAL LABELS, not access boundaries and not a \
delivery mechanism. No membership/ACL: any agent in the workspace can read/post \
to ANY channel. They only TAG a message by topic; they do NOT decide who \
receives it - that is the message TARGET. Only "general" exists by default; \
create channels with channel_create (idempotent by name); list with \
channel_list.

YOUR INBOX (how you receive messages). Messages addressed to you land in your \
GLOBAL inbox and stay until you read them - no cursor, regardless of which \
workspace they were sent in. The loop: inbox_count (if unread > 0) -> \
inbox_pull (returns bodies, leases the batch) -> inbox_ack what you handled \
(unacked messages are REDELIVERED). After sending a message that expects a \
reply, just check your inbox on a later turn - the reply lands there. Lanes, \
leases, redelivery, peek/history and receipt mechanics: \
okto-nexus://reference/tool-docs/inbox.

DELIVERY & READ RECEIPTS. message_create's response IS your delivery \
confirmation: ``recipients`` names exactly who got it; ``delivered_count`` \
totals it. When a recipient seems silent, check message_status(message_id=...) \
INSTEAD of re-sending; or await the sender-only receipt events with \
event_wait(project_root=..., agent_id=<you>, stream="workspace", \
cursor=<from event_cursor>, filters={"type":"message.read"}, \
timeout_seconds=25) and match payload.message_id. By default (opt-out knob \
inbox_read_receipts) an acknowledging recipient ALSO lands a compact \
"message.read_receipt" notification in YOUR OWN inbox - informational; \
inbox_ack it and move on. Full receipt mechanics: \
okto-nexus://reference/tool-docs/inbox.""",
)

add_resource(
    slug="monitoring",
    name="Monitoring & event listening",
    description="event_get/event_wait observability vs the inbox, MCP background listeners, EPT remote pollers for wake-capable harnesses, monitor invariants, reference loops, and anti-patterns.",
    version="5",
    body="""\
# LISTENING FOR EVENTS (observability vs delivery). event_get/event_wait \
OBSERVE the bus; they are NOT how you receive messages addressed to you - that \
is the inbox. Anchor with event_cursor first (pre-flight step 4), then pick a \
mode:
  * Snapshot polling (default): event_get between turns, cursor -> next_cursor.
  * MCP long-poll listener: event_wait(timeout_seconds=N>0, cursor=...); loop \
on next_cursor.
  * EPT remote poller: poll_token_issue -> a separate read-only background \
process on GET /api/v1/events (never sees the permanent nxs_ key).
  * Targeted wait: event_wait with filters (e.g. {"type":"handoff.completed"}) \
and a short timeout to await one specific outcome.
Tool semantics (streams, filter keys, cursor/limit defaults, the long-poll \
ceiling): okto-nexus://reference/tool-docs/events.

# MONITORING FROM A CAPABLE HARNESS. Pick ONE supported shape:
  * IN-PROCESS MCP LISTENER: start a background/parallel task whose ONLY job is \
to call the event_wait TOOL (timeout_seconds=N>0, cursor=<last next_cursor>) on \
THIS MCP connection, then re-arm from next_cursor. The permanent key never \
leaves the MCP transport, and the task may also call session_heartbeat.
  * REMOTE EPT POLLER: when the harness can run a background process that wakes \
the main harness on output, issue an ephemeral poll token with \
poll_token_issue(session_id, session_secret). Give ONLY the returned nxsept_ \
token and base_url to the process. It uses Authorization: Bearer <nxsept_...> \
on GET /api/v1/events?cursor=...&timeout_seconds=25&profile=summary and \
GET /api/v1/inbox/count. It cannot call MCP and cannot mutate anything. Renew \
with poll_token_renew before expires_at; revoke with poll_token_revoke on \
teardown.
  * SINGLE-THREADED HARNESS: poll event_get + inbox_count between turns.

# MONITOR CONTRACT - the 6 invariants a REUSABLE monitor must hold. A monitor \
is nothing but the agent's own identity calling event_wait in a loop whose ONLY \
job is to WAKE the reasoning loop; these invariants keep that loop from lying \
about delivery, presence, or identity.
  * I1 SAME IDENTITY: run as the SAME agent. For MCP listeners this means the \
same authenticated MCP connection. For remote pollers this means an EPT issued \
from THIS session; the server binds the token to your agent_id/workspace_id and \
the process cannot override them. Never give a monitor a different agent key.
  * I2 TWO PLANES, ONE TRUTH: event_* is the SIGNAL plane (observability); \
inbox_* is the DELIVERY plane (authoritative, global by agent_id, durable). The \
event WAKES you; the inbox DECIDES. Confirm every wake with inbox_count/ \
inbox_pull - never treat an event payload as receipt. A dropped event never \
loses a message (it is in the inbox), so one inbox_count per turn covers \
restart/gaps for free.
  * I3 PRESENCE IS EXPLICIT: neither event_wait nor EPT reads advance your \
strong session heartbeat, so an idle session goes stale after \
session_stale_ttl_seconds (default 60s) and drops out of the broadcast audience \
after presence_ttl_seconds (default 1800s). An MCP listener may call \
session_heartbeat each loop. An EPT process cannot: it records only weak \
observer activity (last_used_at) and exists to WAKE the harness, which should \
heartbeat on its next MCP turn. Direct messages still reach the inbox regardless \
of presence; presence governs only the broadcast audience and online indicator.
  * I4 CURSOR ONLY ADVANCES: anchor ONCE with event_cursor (= now), then only \
move forward to next_cursor. Never reset to 0 (replays the whole log) except a \
deliberate cold catch-up. On restart, persist the last next_cursor for no-loss, \
or re-anchor at now and let inbox_count sweep the backlog (I2 makes that safe).
  * I5 ENVELOPE ALWAYS, TIMEOUT IS NOT AN ERROR: every call returns \
{ok:true,data} or {ok:false,error} - branch on ok BEFORE touching data. An \
empty page is a timeout is the STEADY STATE (re-arm and continue). A transport/ \
hub-restart error is a BOUNDED backoff then re-arm from the last good cursor - \
never a tight retry loop.
  * I6 WAKE, DON'T CONSUME: the monitor observes and wakes; keep inbox_pull/ \
inbox_ack (they MUTATE read-state and emit message.delivered/message.read \
receipts) in the agent's own turn, where processing and acknowledgement stay \
coupled. EPT endpoints deliberately expose only read-only events/cursor/count/ \
peek and never return message bodies.

# REFERENCE MONITOR - explicit and copy-ready. Convention: call(tool, args) \
performs ONE MCP tool call on the agent's OWN connection (I1) and returns the \
raw envelope dict {"ok": bool, "data"|"error": ...}. Every field access below \
is the real envelope shape - nothing is elided.

  # --- setup (once) ---
  me   = call("agent_whoami", {})["data"]["agent_id"]
  ws   = call("workspace_resolve", {"project_root": PROJECT_ROOT})["data"]["workspace_id"]
  sess = call("session_open", {"agent_id": me, "workspace_id": ws})["data"]
  # keep sess["session_secret"] - required by inbox_pull/ack in trust_mode=strict (I6)
  cursor = call("event_cursor",
                {"project_root": PROJECT_ROOT, "agent_id": me,
                 "stream": "workspace"})["data"]["cursor"]           # I4: anchor at "now"

  # --- loop ---
  backoff = 1
  while running:
      r = call("event_wait", {
          "project_root": PROJECT_ROOT, "agent_id": me, "stream": "workspace",
          "cursor": cursor, "filters": {"type": "message.created"},
          "timeout_seconds": 25, "profile": "summary",              # 25 <= ceiling 30s
      })

      # I3: presence is the monitor's job - event_wait/inbox_count do NOT advance
      # your heartbeat. Do this EVERY turn (< 60s cadence) or the agent goes stale.
      call("session_heartbeat", {"session_id": sess["session_id"], "workspace_id": ws})

      if not r["ok"]:                                                # I5: transient hub error
          emit({"type": "nexus.monitor.error", "error": r["error"]})
          sleep(min(backoff, 30)); backoff = min(backoff * 2, 30)
          continue
      backoff = 1

      data = r["data"]
      if data.get("next_cursor") is not None:                       # I4: only ever forward
          cursor = data["next_cursor"]

      # I2: the inbox is the source of truth - confirm on wake AND on timeout
      # (an empty page is normal; a dropped event never loses a durable message).
      count = call("inbox_count", {"agent_id": me})["data"]
      if count["unread"] > 0:
          emit({"type": "nexus.inbox.unread", "unread": count["unread"]})
          # I6: WAKE only - do NOT inbox_pull/ack here. The agent's main turn
          # consumes; pull/ack mutate read-state and emit delivery/read receipts.

  # --- teardown ---
  call("session_close", {"session_id": sess["session_id"], "workspace_id": ws})

# EPT REMOTE POLLER - for a background process that can wake the harness. The \
main harness performs setup over MCP and passes ONLY token/base_url/cursor to \
the process. The process performs ordinary HTTP GETs with Authorization: Bearer \
<token>; it never sees the permanent nxs_ key.

  # --- MCP setup in the harness ---
  issued = call("poll_token_issue", {
      "session_id": sess["session_id"],
      "session_secret": sess["session_secret"],
  })["data"]
  token = issued["token"]               # raw nxsept_ value - returned once
  base  = issued["base_url"]            # "/api/v1" relative to the hub origin
  cursor = http_get(base + "/events/cursor",
                    bearer=token)["data"]["cursor"]

  # --- background process loop ---
  while running:
      r = http_get(base + "/events?cursor=%s&filters=type:message.created&timeout_seconds=25&profile=summary" % cursor,
                   bearer=token)
      if not r["ok"]:
          wake_harness({"type": "nexus.monitor.error", "error": r["error"]})
          sleep(2); continue
      data = r["data"]
      cursor = data.get("next_cursor", cursor)
      count = http_get(base + "/inbox/count", bearer=token)["data"]
      if count["unread"] > 0 or count.get("handoffs_pending", 0) > 0:
          wake_harness({"type": "nexus.wake", "count": count, "cursor": cursor})

  # --- MCP teardown in the harness ---
  call("poll_token_revoke", {
      "session_id": sess["session_id"],
      "session_secret": sess["session_secret"],
  })

ANTI-PATTERNS - never do any of these; each re-implements, worse, what one tool \
call already does, and most break your identity or presence:
  - NO raw HTTP with the permanent nxs_ key. Raw HTTP is allowed ONLY for the \
EPT data-plane endpoints with a short-lived nxsept_ token.
  - NO `okto-nexus tail` (or any CLI) as a listener. It is a PASSIVE operator \
console, does not count as presence, and is not an agent surface.
  - NO standalone monitor that stores the permanent key or calls MCP. A \
separate process is acceptable only as an EPT poller whose output wakes the \
harness.
  - NO spawning a helper process or a second server. The hub is already \
running and this MCP session is your only required channel.""",
)

# C2: register the tool-docs + target-grammar resources (side-effect import
# at the bottom so add_resource is already defined when resources_docs runs).
from . import resources_docs as _resources_docs  # noqa: E402,F401
