# ADR 0003: Canonical control targets and interrupt containment

Status: implemented for steer, interrupt and policy close in the R4 development
path with Core 0.2.27.dev0. Full Core and product conformance remain outstanding.

## HTTP and wire projection

The HTTP `Target` remains an object with `kind` and `expected_turn_id`.
The NXL frame uses the Core field `expected_turn_id`. The Server projects
the target before calling the Core hash function. It does not maintain a
second hashing algorithm. The native turn ID is therefore covered by the
same hash at resolution, admission, dispatch and receipt publication.

The Server calls Core `validate_control_target` at resolution, admission
and dispatch. It has no adapter-specific targeting table. A native ID uses
`native_turn_id`; a supported ID-less active-run control requires explicit
`current_run`. A missing target is never interpreted as consent to control
an arbitrary active run. Core and the native adapter revalidate the actual
turn at the write frontier.

The Connector includes the requested target in resolution and checks the
returned action, target, session, content, scope and Core hash before it
can submit the returned operation. A self-consistent response with a
different target is still rejected.

## Interrupt reason

`ResolveIntentRequest` already has optional `text` and has no `reason`
property. For interrupt, the Server maps provided `text` to payload
`reason`, without translating, truncating or otherwise rewriting it.
Absent text becomes `Interrupt requested by the authorized agent.`
The HTTP shape stays unchanged; additional reason, PID, signal, argv and
environment fields are not accepted.

Core 0.2.27 accepts the normative 0–1024 character range. Empty text is
preserved; only absent text receives the default. The temporary blocker
`core_interrupt_reason_unsupported` used with Core 0.2.26 is removed.

## Authority and containment

An admitted interrupt or close uses the independent control reservation. Dispatch
still requires the current agent authority, binding, realization, session
owner, applied lease, allowed action, connection, unrevoked source grant
and valid lane. The lease deadline alone does not prohibit containment.
Discovery freshness is not needed to contain an already opened session.
No caller-supplied containment flag or extra permission is introduced.

The dispatch checks the full Core frame before consuming the productive
budget or committing `SENDING`. Interrupt does not spend a productive
execution, but must remain allowed by the canonical grant. An already sent
reservation cannot be used for a second send. Receipt history keeps the
original operation ID and hash.

## Per-operation close policy

Resolution maps optional HTTP `text` to `reason` and fixes the canonical
policy at 30 seconds of drain and 15 seconds of interrupt. Absent text becomes
`Close requested by the authorized agent.` No new HTTP fields are introduced.
All three payload fields are hashed and verified by the Core projector.
`r4_close_operation` produces a typed `CloseOperation` without losing policy.

Core owns one close producer per session and coalesces same-ID waiters.
Cancellation detaches observation; another policy under the same ID conflicts.
Draining fences productive operations. An observation deadline can return
`OUTCOME_UNKNOWN` while the producer continues; it cannot manufacture success.
Managed force uses the existing independent owner; attach is not force-stopped.

Only a matching, authorized `SUBMITTED`/`SUCCEEDED` close receipt from the
current executor owner projects a ready session to `CLOSED` and closes its
lease. Receipt insertion, outbox release and session projection share one
transaction. Progress and unknown receipts do not close the session; retry
after a projection failure repeats the same receipt rather than native close.

## Remaining contract and product work

Public close effects wait for their journal frontier. Containment during
pending lease CAS and blocked initial durable admission remains explicit
follow-up work; the independent runtime shutdown path remains available.

Core 0.2.53.dev0 promotes the executable R4 bundle after installed contract
and consumer conformance. Server readiness now checks that verified bundle
and its explicit R4 revision independently of historical R3. Installed
dispatcher and daemon tests use a strict synthetic native peer; native
providers, separate hosts, UI/CLI acceptance and the final release gates
remain separate requirements. See the current M13 reconciliation evidence.
