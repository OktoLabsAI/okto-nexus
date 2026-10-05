# NS15.03 canonical conversation delivery — October 1, 2026

The existing MCP message entry point can now deliver to an approved canonical
conversation endpoint in its logical workspace. The message, existing inbox
push claim, causal reservation, execution intent, opening/turn operations and
R4 outbox are committed in the same transaction. Failure after operation
admission rolls all of these back. No second inbox or agent credential is made.

Schema 094 links each canonical opening/turn to its existing delivery operation.
The recipient's current execution grant remains required. The sender credential,
audience, message policy, endpoint/profile approval, claim and causal deadline
are revalidated before dispatch and initial opening lease authorization. The
legacy dispatcher excludes these mapped deliveries; only the R4 owner calls Core.
The complete delivery envelope supplies identity, causal references and content
as context, without conveying tool authority.

An opening creates a durable initial-turn child; an established ready session
receives a turn directly. Subsequent deliveries wait for the earlier delivery's
terminal receipt, not its submitted acknowledgement. Authenticated receipts
project acceptance, uncertainty or terminal outcome onto the logical delivery;
pre-send refusals remain refusals. Canonical terminal provenance has a separate
column, preserving historical native-event foreign keys. Capacity accounting
excludes terminal canonical deliveries. Native completion does not complete a
handoff or create a result notification.

Directed public-MCP tests cover opening plus turn, native payload/correlation,
queued session reuse, terminal receipt projection, sender revocation, rollback
before and after canonical writes, and non-executing observer endpoints.
Migration tests reconstruct schemas 091–093 on copies of actual R4 history and
verify repeated upgrade, preserved operations/receipts and foreign keys.
Installed campaigns and package hashes are recorded in
[the manifest](test_runs_20261001_ns15_03_delivery.json).

This is partial NS15.03/NS06.05 integration. The public message journey tested
here selects an existing path-based logical workspace when preparing the R4
binding. Path-free message selection for newly created logical workspaces,
mixed canonical/legacy endpoint selection parity, managed handoff delivery,
context-only observer transport, result/event publication and real remote/provider
qualification remain to be completed. Native peers and readiness qualification
are fixture-local. Normative TR4-15-03, TR4-06-05 and release gates remain open.
