# ADR 0003: Canonical control targets and interrupt containment

Status: implemented for steer and interrupt in the R4 development path.
Runtime close policy and full Core conformance remain outstanding.

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

The normative interrupt payload permits up to 1024 characters. Core
0.2.26 currently requires 1–256. Nonempty reasons of 257–1024 characters
produce a durable blocked resolution (`core_interrupt_reason_unsupported`)
instead of an invalid native operation. Empty-reason conformance also
remains open. These are implementation gaps to fix in Core conformance,
not permanent reductions of the delivery requirements.

## Authority and containment

An admitted interrupt uses the independent control reservation. Dispatch
still requires the current agent authority, binding, realization, session
owner, applied lease, allowed action, connection, unrevoked source grant
and valid lane. The lease deadline alone does not prohibit containment.
Discovery freshness is not needed to interrupt an already opened session.
No caller-supplied containment flag or extra permission is introduced.

The dispatch checks the full Core frame before consuming the productive
budget or committing `SENDING`. Interrupt does not spend a productive
execution, but must remain allowed by the canonical grant. An already sent
reservation cannot be used for a second send. Receipt history keeps the
original operation ID and hash.

## Remaining contract and product work

The normative `ClosePayload` requires `drain_seconds` and
`interrupt_seconds`; Core 0.2.26 accepts only `reason`. Its native
`CloseOperation` also has no per-operation policy. Implement, hash, enforce
and test that policy in Core before composing canonical close. Do not
silently discard the normative fields or claim policy enforcement from the
runtime's separate global shutdown settings.

The R4 executable and Server readiness gates remain false. Tests qualify
these application services with installed Core and a strict native test
peer. They do not demonstrate a dispatcher loop, daemon, native provider,
separate hosts, UI/CLI completion or final release acceptance.
