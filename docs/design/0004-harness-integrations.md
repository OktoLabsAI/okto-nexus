# 0004 — Native harness connections for canonical Nexus agents

- Status: amended for 0.2.0; implementation in progress, final gate not passed.
- Original date: 2026-09-20. Amendment: 2026-09-23.
- Implementation branch: `feature/v0.2.0`.
- Extends [0001](0001-message-inbox-delivery.md). Supersedes the earlier revision of
  this ADR, available in Git history, including its implicit registration,
  ambient-provider, unrestricted broadcast and approval-bypass instructions.
- Authority: the accepted PR34 remediation package, especially
  [contracts and states](../../02_CONTRATOS_E_ESTADOS.md) and
  [source traceability](../../06_FONTES_E_RASTREABILIDADE.md).
  Amendment decisions are not retroactively attributed to the original review.

## Context

PR34 introduced Pi/RPC, Codex/app-server, Claude stream-json and private Claude
attach. Native connectivity must preserve canonical Agent identity, authorization,
logical inbox delivery and executable handoff ownership. Process sessions and
transport attempts cannot become alternative identities or task queues.

This amendment records the target architecture and the implemented guarantees
separately from pending gates. [Execution status](../../plans/pr34-remediation/IMPLEMENTATION_STATUS.md)
is authoritative for current evidence. Historical captures are not authorization
to reuse a provider, LAN endpoint, token or interactive session.

## Decisions

### D1 — One serve owner, durable work and event-driven native transport

The in-process supervisor is owned by one `serve` instance per store. An owner
lease/epoch, journal writer lock and process ownership enforce this boundary.
Authenticated stdio producers use the owner proxy and bounded IPC wake path.
Canonical writes persist transport intents in the same transaction; native calls
occur after commit. Lost wakes are recoverable from durable state.

Native send and response capture use protocol events, not native status polling.
Bounded internal database recovery, timeouts and existing long-poll APIs remain.
The claim is event-driven native delivery, not absence of every timer or poll.

### D2 — Versioned adapter contracts preserve topology differences

The registry describes adapters, trusted local factories, configuration validation
and capabilities. Envelopes carry canonical sender/recipient, workspace, intent,
operation/attempt lineage and untrusted content. Adapters translate native payloads.
An Agent has endpoints; an endpoint may have runtime sessions; a physical Codex
connection may multiplex sessions. These are distinct records and lifetimes.

The four adapters remain available within their demonstrated limits. An extension
must use registry contracts rather than add product switches to the domain.
Surface52 intersects trusted probe observations with descriptor capabilities and
approved profile restrictions. An extension without a probe cannot execute merely
because its descriptor advertises conversation. No descriptor grants permission.

### D3 — Existing identity and authenticated authority precede runtime creation

Runtime opening requires an existing active Agent and an approved endpoint/profile.
It must not upsert role, skills, tags or profile metadata. RequestContext derives
from authenticated Nexus credentials; payload agent IDs do not authenticate anyone.

Operator administration and scoped agent grants share canonical policy checks.
Grant scope, actor, represented Agent, workspace, endpoint/profile revision,
expiry/revocation and budgets constrain execution. A native subprocess never
receives the Nexus operator credential. Internal publication does not upgrade
a denied caller into operator authority.

### D4 — Pi retains its RPC event stream

The Pi adapter consumes bounded JSONL frames and preserves turn-boundary steering,
interrupt/settle behavior and native events. Native ACK, resume and deduplication
must be demonstrated before use. Current remediation Pi native campaign is
NOT_RUN; protocol fixtures do not constitute a real-provider campaign.

### D5 — Provider and environment selection belong to approved profiles

There is no designated LAN provider or personal account in this architecture.
Profiles default to disabled and no ambient inheritance. The operator configures
an isolated tool home, executable, provider/model and supported secret references
for the intended scope. Secret resolution and process/network calls occur outside
SQLite write transactions. Sandbox and approvals cannot be disabled just to pass
a test. Configuration changes revoke old grants and boot approvals.

### D6 — Codex uses app-server with connection and turn correlation

Codex uses its native app-server transport. Thread/session IDs remain distinct
from physical process identity. Early events, turn starts, command writes and
terminal results are correlated to durable operations and owner epochs. Closing
one thread must not terminate an active sibling. Process restart does not imply
thread survival, resume support or permission to repeat an uncertain send.

Supported native permission/input requests use durable correlation and canonical
operator HITL. No unattended approval bypass is part of this decision. Evidence
must identify actual binary versions and exercised scenarios, not assume every
experimental method exists or behaves identically across releases.

### D7 — Claude stream and attach remain distinct

Stream-json is the managed bidirectional path, with bounded framing and native
events. Supported permission requests and AskUserQuestion use explicit canonical
decisions; human approval, native delivery and work completion remain separate.

Private cc-socks attach is separately enabled and requires an operator-selected
external interactive session on a supported POSIX platform. It is send-only:
transport write is not acceptance or completion. No reply, steer, interrupt,
observed process termination or correlated result is fabricated. Detach does not
kill the external session. Protocol drift fails explicitly without removing the
other connectors. Dedicated native attach verification remains NOT_RUN.

### D8 — Boot and on-demand opens share approved bindings and owned lifecycle

Endpoint configuration alone does not spawn a process. Explicit boot approval
binds current configuration revisions; on-demand opens enforce equivalent access.
Opening reserves state, starts/attaches outside the writer transaction, then
persists readiness and correlation. A saved attach PID is not boot authorization.

Managed children use birth-time ownership on Windows and Linux. Startup failures,
reader faults and cancellation retain enough ownership to reap owned processes.
Shutdown quiesces admission, drains activity and the journal, then releases owner
resources. Undrained activity remains pending. Unknown is not rewritten as ended
because a lease or timeout elapsed; there is no arbitrary PID scanner cleanup.

### D9 — Shared optional MCP/REST application surfaces

The eight optional harness tool names and their REST facades reuse application
authorization and use cases. Feature-off blocks new admission, including cached
handlers. Existing operations can still drain/recover in maintenance mode.
Fresh feature-off MCP omits harness tools; operator REST supports recovery.

Schema revisions and reference resources are versioned, with actual OFF/ON
surface measurements. Safe discovery groups endpoints under canonical identity
without exposing private paths, metadata, environment or secret references.
Endpoint declarations remain not_probed; each current-owner ready session exposes
its qualified effective capabilities. Persisted readiness is not process liveness.

### D10 — Inbox, journal, results and handoffs retain separate responsibilities

Inbox is logical delivery. Outbox tracks its transport attempts and commands.
One reservation prevents competing push/pull execution. Uncertain acceptance
holds that reservation; timeout does not authorize fallback. Journal capture
precedes event/result projection, with bounded retention, stable correlation,
recovery boundaries and explicit gaps. A correlated terminal can consume its
own reservation; a socket write cannot.

Results default to private correlated replies under current audience/authority.
Explicit bounded conversation relay preserves causal roots, budgets and deadlines
across slow chains and restart. New independent requests may create new roots;
late continuation cannot mint a fresh budget. There is no unrestricted broadcast
or blanket ban on legitimate harness communication.

Executable work remains canonical handoff/claim/grant work. Native terminal text
does not automatically complete it. Authenticated explicit calls or the configured
structured result contract request canonical completion/rejection; verification
stays separate. Human approval is not a synthetic native ACK.

Operator recovery uses exact snapshots, idempotency, reason and explicit risk
acknowledgement. Conversation takeover releases the original inbox item without
native replay; command abandonment retains history. Recovery quarantines endpoints
and revokes grants/boot. Late results remain durable but cannot use abandoned
authority. Explicit managed-claim recovery reopens the same CLAIMED handoff,
fences its abandoned attempt and requires a fresh claim without replaying work.
VERIFYING and terminal canonical states cannot be reopened this way.

## Consequences and acceptance

SQLite migrations are additive (current schema056), with no destructive reverse
migration used as rollback. Production composition, authorization parity, lost
replies, restart, journal/ownership and transaction boundaries require integration
evidence. Fixture success is reported separately from actual provider/model runs.

Use the [operator guide](../harness-integrations/operator-guide.md) and
[administration reference](../harness-integrations/runtime-administration.md) for
implemented workflows. Remaining effective probes,
backup/restore, advanced native campaigns and full P12 matrix must
pass their applicable gates before release. Pi/attach external limits remain
explicit NOT_RUN, never converted into PASS. No A2A server, external broker,
cloud runtime or new task orchestrator is introduced.

## 0.2.0 remediation contracts (surface58 / schema064)

The original protocol decisions above remain historical context. The current
application contract uses one canonical Agent identity, persistent endpoints,
approved execution profiles and separate runtime bindings. Authenticated REST,
MCP HTTP, stdio owner proxy and internal commands share authorization and current
grants; payload identity never authenticates a caller.

The canonical inbox owns logical delivery. A transactional outbox records bounded,
owner-fenced transport attempts, with explicit unknown/unconfirmed states and no
ambiguous replay. Event ingress is journaled before idempotent projection; native
turn completion is separate from canonical handoff completion and verification.

Optional context observation v1 is nonexecuting and requires a trusted descriptor
plus verified capability. No built-in native adapter is assigned that capability.
Attach external work v1 instead uses a separately authenticated, operator-approved
canonical Nexus session for claim/ACK/complete. Its native socket capabilities
remain unchanged. Migration064 fences older writers and preserves referenced
session history. These are new integration decisions, not capabilities inferred
from the peer protocols.

See the [contract map](../../plans/pr34-remediation/CONTRACT_MAP.md),
[finding/evidence audit](../../plans/pr34-remediation/P12_FINAL_AUDIT.md), and
[operator guide](../harness-integrations/operator-guide.md). Native qualification
is version/configuration-specific; Pi and dedicated attach remain NOT_RUN in the
current authorized campaign. No A2A server, remote broker or new task orchestrator
is introduced by this remediation.
