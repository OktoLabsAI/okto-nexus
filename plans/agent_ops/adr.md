# ADR: product operations without a second execution system

Status: accepted for implementing R3; scope and gates remain the root plan.

## Identity and product dimensions

`agent_id` remains the canonical identity. Coordination participation, execution
owner, activity provenance, presence, observation freshness, reservable capacity
and authority are independent dimensions. Multiple sessions or external
instances do not overwrite agent identity or global availability. The default
generalist preset resolves into ordinary reviewed product configuration;
reconnect reads those same objects and never reapplies defaults.

## Canonical sources and auxiliary state

Attention is a bounded read model over approvals, native requests, execution,
handoffs, delivery and recovery. Episode identity derives from stable source
facts/revisions; only seen/snooze preferences are additional durable user state.
GET does not approve, claim, reply, replay or resolve. Actions call existing
canonical endpoints, which revalidate authority and revision.

External observations are strictly telemetry. Restricted publishing credentials
are accepted only for observation ingress; no native receipts, capacity, MCP
heartbeat or completion can be manufactured by idle/done, timeout or silence.
Herdr is an optional read-only source. Unknown provenance/occupant invalidates a
mapping rather than transferring another agent's identity.

## Configuration and interaction

External participant configuration is a separate pure contract from managed
`HarnessHTTPTemplate`. It may reuse safe rendering/file CAS primitives, never
pretend a permanent agent key is `mcp-cap:` or relax native qualification.
Effects on Server, local credential store and client files are separate recorded
steps, not a distributed transaction. Managed configuration reuses Finish.

PR-04 places the reference-only participant description in Core's separate
`participant_config` module for reuse by both hosts. It records client/version,
format revision, selected file scope and approved origin. JSON/TOML planning
shares structural editors with managed configuration; managed capability and
native qualification checks remain intact. Generic export is a manual
instruction, and real-client config parsing is separate from secret resolution,
MCP negotiation, session participation and productive work.

Human prompts use canonical native operations; inter-agent work uses handoffs.
CLI saves request identity before transport, inspects the same ID after response
loss, and uses existing receipts where their scope proves deduplication. Generic
message/handoff creation needs its own transactional request receipt. Waiting
ends only observation; it cannot imply cancellation or productive retry.

## Instance and supervisor

Resolve local/remote topology before any process start. Remote failure never
creates a substitute local Server. Canonical configuration/data paths, component
and effective OS user define the service instance, distinct from agent/workspace.
Both the home and shared database must be protected against duplicate writers.
OS-held exclusion is authoritative, not heartbeat age, a cached PID or open port.
Readiness correlates instance/generation and active version after bootstrap and
runtime reconciliation; uncertainty blocks the affected execution scope.

On-demand background and opt-in user service invoke the same application
foreground entrypoint. An installed OS supervisor owns start/recovery; no
parallel detached supervisor is started. Per-instance definitions include owner
and revision and never overwrite external edits. Persist executable/configuration
references, not secret values or the whole calling environment. Status/logs/
doctor never start the service or inference. Closing a client never stops work.

## Stop, recovery and portability

Reuse Server admission fence/shutdown coordinator and Connector shutdown/IPC.
Request drain before asking an OS manager to stop; keep decisions/results and
reconciliation available while draining. Deadline expiry reports pending/unknown
work and does not force kill or release ownership. Restart waits for that same
protocol; it does not renew grants or replay uncertain effects. Native child
containment follows Core's actual ownership contracts.

Qualify terminal independence, crash recovery, login, logout and boot separately.
Initial target is Windows user logon task, not a Windows Service or unattended
boot guarantee. Templates alone do not qualify Linux/macOS. Service uninstall
preserves history and credentials. Upgrade must compare active/installed versions
and preserve instance exclusion; database rollback is never assumed safe.
