# M3l — Isolate failed startup after session authorization

A synthetic Pi preparation timeout reproduced agent-wide containment: opening
a second session stopped a healthy session of the same agent. The original
test failed on `healthy_peer.stopped`. Production's `version_probe_timeout`
motivated this reproduction; it does not establish the cause of that timeout
or of the user's simultaneous Recovering report.

The dispatch owner now sends failures of a known authorized session to its
retained session recovery worker. It records the original sanitized cause and
session ID. The authorized executor is retained before acknowledging the lease
in Server, so an acknowledgement failure cannot lose its containment identity.
Publication and event recovery use the exact session scope. The successful
failed-open path also drains only that session's events.

After stopping native resources and joining the exact operation/renewal
producers, recovery distinguishes failed preparation from a native opening.
Preparation requires absent binding/stream, empty Core claims/receipts and
released physical ownership. Native openings still require the existing
durable no-effect or exact stop/release proof and contiguous committed stream.
Missing receipts do not fabricate closure or release capacity. Uncertain
sessions retain their own recovery worker while healthy siblings can operate.

The installed campaign passed 34 cases with unchanged inputs and exact package
byte verification. It includes all three adapters, healthy sibling turns,
subsequent openings, original-cause diagnostics, deliberately held containment,
unknown receipts, failed-opening restart, retained-resource rejection, agent
isolation, publication lag and real disposable process termination/restart.
Provider responses were simulated in these fixtures; this is a technical
checkpoint, not completion of the real Meta-harness UI gate. See
`m3l-results.json` for exact scope, artifact hash and campaign paths.

Only Nexus product code changed. Core and Connector retain their previously
qualified dependency wheels. The isolated validation environment was updated;
the global Nexus installation was not restarted or upgraded.

M3 and L20 remain in progress. Failures before a session receives its authorized
executor and consumed-capacity startup cases still need qualification. Connector
`R4ExecutionOwner._produce` can close the whole control connection when
preparation fails before `_capacity_bindings` contains a durable receipt
binding; `_execute_with_recorded_outcome` only preserves exact OUTCOME_UNKNOWN
facts. Reproduce and qualify that path in M5 before extracting shared lifecycle
policy. No claim of complete local/remote parity is made here.
