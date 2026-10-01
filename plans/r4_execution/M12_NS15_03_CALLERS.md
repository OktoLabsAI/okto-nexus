# NS15.03 canonical session callers — October 1, 2026

This is a partial cutover increment, not TR4-15-03 acceptance. Existing MCP
`harness_send`, `harness_steer`, `harness_interrupt`, `harness_close` and
`harness_get`, and their REST counterparts, now recognize canonical sessions.
They use the existing R4 resolver, durable operation admission, dispatcher and
public Core targeting contract. They do not construct a native connector.
Operation and session reads use the canonical durable projections.

The compatibility entry retains endpoint/grant authorization before admission.
R4 continues to enforce subject scope, revisions, readiness, leases and dispatch
authority. Stable idempotency keys are required. Legacy operation/owner guards,
unknown turn payload members and inapplicable turn targets are rejected rather
than discarded. Core determines active-run versus native-turn targeting.
Ambiguous session IDs fail closed. Inventory freshness is shared with the HTTP
owner through the dependency container; there is no second inventory publisher.

The technical campaign opens through the public canonical API and exercises
existing REST and MCP commands, replay, durable reads and close. A sentinel on
the old control service proves that canonical commands do not reach it. Negative
cases cover grants, disabled endpoints, production readiness, unrelated callers,
missing keys and incompatible legacy parameters. Production readiness remains
false; the fixture qualifies a synthetic native peer only.

Test preparation initially used a Host rejected by MCP transport security and
assumed R4 admission itself checked legacy grants. The latter exposed the need
to retain the compatibility entry's endpoint authorization explicitly: R4 lease
issuance remains a separate execution authority stage. The final tests retain
both revoked-grant and disabled-endpoint cases.

Open callers, boot/delivery callers, event projection parity and removal of the
old native loaders/codecs remain outstanding. The existing legacy execution path
is still present for unconverted callers. Historical drain and domain services
are preserved. No schema change, Core wheel change, Connector application import,
or release gate closure is included. See the installed runner and manifest for
artifact hashes and results.
