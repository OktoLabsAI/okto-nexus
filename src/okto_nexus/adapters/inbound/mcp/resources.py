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
    return f"---\nversion: \"{version}\"\n---\n\n{body.strip()}\n"


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
    version="1",
    body="""\
# PRE-FLIGHT - run this EXACT sequence on your FIRST turn, in order, BEFORE \
starting whatever the user asked. It is cheap and idempotent; every agent \
bootstrapping the same way is what makes the swarm predictable.

1. IDENTITY - agent_whoami(): your agent_id, operator-assigned role, \
capabilities and the permissions in effect. Use that agent_id everywhere. Only \
if you must advertise NEW capabilities for routing, follow with agent_register \
on your OWN id (self-only: minting/modifying other identities returns \
PERMISSION_DENIED - identities are created on the dashboard).

2. PRESENCE - workspace_resolve(project_root=<cwd>) then session_open(\
agent_id=<you>, workspace_id=<resolved>). Without an open, heartbeat-fresh \
session you are NOT in the broadcast audience (messages to "everyone" silently \
skip you) and the dashboard shows you offline. Pass your session_id + \
session_secret on every authenticated verb: each one advances your heartbeat, \
so working (receiving, sending, claiming) keeps you present - reserve an \
explicit session_heartbeat for IDLE turns. Store the returned session_secret.

3. BACKLOG - inbox_count(agent_id=<you>); if anything is pending, inbox_pull \
and triage what accumulated while you were offline (redeliveries included), \
then inbox_ack what you handled. Never skip this: senders are already tracking \
these deliveries.

4. MONITOR - anchor first: event_cursor(stream="workspace") returns the log's \
current end, so you only ever see events from NOW on. Then, if your harness \
supports background/parallel calls, run an event_wait(timeout_seconds=N, \
cursor=<anchor>) long-poll loop IN THE BACKGROUND (see the monitoring \
resource); otherwise poll inbox_count + event_get(cursor=<anchor>) between \
turns, advancing the cursor.

THEN follow the user's instructions. When your work is finished for good, \
session_close (presence must reflect reality).""",
)

add_resource(
    slug="communication",
    name="Communication & inbox",
    description="How to choose a channel (direct/handoff/broadcast), channels, the inbox reception loop, and delivery/read receipts.",
    version="1",
    body="""\
# HOW TO COMMUNICATE - prefer the most targeted, least noisy channel.

1) DIRECT MESSAGE (default, preferred). message_create with \
target={"strategy":"direct","agent_id":"<recipient>"}. Most efficient, least \
noise. ALWAYS reply DIRECTLY to whoever messaged you (target their \
from_agent_id) unless you explicitly mean to broadcast or hand off.

2) HANDOFF (when exactly ONE free agent should take the work). handoff_create \
with a capability/role/broadcast target: every eligible agent SEES it but only \
the first to handoff_claim gets it (others get HANDOFF_ALREADY_CLAIMED); an \
unfinished claim's lease expires and the work returns to the pool. Example: \
"OCR this scan" -> handoff target {"strategy":"capability","capability":"ocr"} \
(find the capability via capability_list first).

3) BROADCAST (last resort). message_create with NO target. Two valid uses: (a) \
DISSEMINATE instructive/contextual info to everyone; (b) open-ended DISCOVERY \
when you do NOT yet know who to ask. Do NOT broadcast actionable WORK requests: \
an undirected "do X" can trigger UNWANTED PARALLEL WORK. Once discovery finds \
the owner, switch to a direct message (or a handoff if it is dispatchable).

CHANNELS are lightweight ORGANIZATIONAL LABELS, not access boundaries and not a \
delivery mechanism. No membership/ACL: any agent in the workspace can read/post \
to ANY channel. They only TAG a message by topic; they do NOT decide who \
receives it - that is the message TARGET. Only "general" exists by default; \
create channels with channel_create (idempotent by name); list with \
channel_list.

YOUR INBOX (how you receive messages). Messages addressed to you land in your \
GLOBAL inbox and stay until you read them - no cursor, regardless of which \
workspace they were sent in.
  * inbox_count(agent_id=<you>) - cheap between-turns check; if unread > 0, pull.
  * inbox_pull(agent_id=<you>) - returns your unread messages WITH body and \
marks them in-flight (leased).
  * inbox_ack(agent_id=<you>, message_ids=[...]) - once handled, move them to \
history. Unacked messages are REDELIVERED (at-least-once). inbox_peek is a \
non-destructive look; inbox_history is the read archive.
After sending a message that expects a reply, just check your inbox on a later \
turn - the reply lands there.

DELIVERY & READ RECEIPTS. message_create's response IS your delivery \
confirmation: ``recipients`` names exactly who got it; ``delivered_count`` \
totals it. Then two trackers:
  * PULL - message_status(message_id=...) returns the per-recipient lane: \
unread / delivered / read (with read_at) / parked. Check it INSTEAD of \
re-sending when a recipient seems silent.
  * PUSH - the inbox emits receipt events visible ONLY to you, the sender: \
``message.delivered`` when a recipient pulls and ``message.read`` when they \
acknowledge. Await one with event_wait(filters={"type":"message.read"}) and \
match payload.message_id.
  * INBOX receipt (default ON; opt out via inbox_read_receipts) - when a \
recipient acknowledges you ALSO get a compact "message.read_receipt" \
notification in YOUR OWN inbox. It is informational - inbox_ack it and move on; \
receipts never generate receipts.""",
)

add_resource(
    slug="monitoring",
    name="Monitoring & event listening",
    description="event_get/event_wait observability vs the inbox, the long-poll listener pattern for capable harnesses, and the anti-patterns to avoid.",
    version="1",
    body="""\
# LISTENING FOR EVENTS (observability vs delivery). event_get/event_wait \
OBSERVE the bus (message.created, handoff.*, session.* events); they are NOT \
how you receive messages addressed to you - that is the inbox. Anchor with \
event_cursor first (pre-flight step 4), then pick a mode:
  * Snapshot polling (default): event_get between turns, advancing cursor -> \
next_cursor. Non-blocking, fits single-threaded loops.
  * Long-poll listener: event_wait(timeout_seconds=N>0, cursor=...) parks the \
call until a matching event arrives or N elapses (clamped to the server \
ceiling), then returns the page; loop on next_cursor. An ordinary \
streamable-HTTP call - safe to use as a wait primitive when you EXPECT an event.
  * Targeted wait: event_wait with filters (e.g. {"type":"handoff.completed"}) \
and a short timeout to await one specific outcome.

# MONITORING FROM A CAPABLE HARNESS (Claude Code & any harness that can run a \
tool call in the BACKGROUND or in PARALLEL). A correct monitor is NOTHING but \
event_wait called in a loop on THIS MCP connection - no daemon, no socket, no \
process to supervise.
  * THE RIGHT WAY: start a background/parallel task whose ONLY job is to call \
the event_wait TOOL (timeout_seconds=N>0, cursor=<last next_cursor>), and \
re-arm it from the returned next_cursor each time it yields. Because the \
long-poll runs OFF your main turn, your reasoning loop is never blocked; \
because the call rides THIS connection, your API key already supplies your \
identity/visibility/permissions. A timeout just returns an empty page - re-arm \
and continue; that is the steady state, not an error.
  * IF YOU CANNOT BACKGROUND A CALL (strictly single-threaded): do NOT fake it \
with an external blocking process - fall back to snapshot polling (event_get \
between turns, advancing the cursor).

ANTI-PATTERNS - never do any of these; each re-implements, worse, what one tool \
call already does, and most break your identity or presence:
  - NO curl / raw HTTP against the REST API (/api/v1), the /mcp endpoint, or \
the dashboard's live SSE stream. Call the event_wait tool instead.
  - NO `okto-nexus tail` (or any CLI) as a listener. It is a PASSIVE operator \
console, does not count as presence, and is not an agent surface.
  - NO standalone "monitor" app/script/worker to poll the bus. A separate \
process does not share your identity/API key, does not keep your presence \
heartbeat fresh, and cannot hand events back into your reasoning loop.
  - NO spawning a helper process or a second server. The hub is already \
running and this MCP session is your only required channel.""",
)

# C2: register the tool-docs + target-grammar resources (side-effect import
# at the bottom so add_resource is already defined when resources_docs runs).
from . import resources_docs as _resources_docs  # noqa: E402,F401
