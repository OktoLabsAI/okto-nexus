# TR4-06-05 domain integration — October 1, 2026

`tests/execution_r4/test_ns06.py::test_ns06_05` now covers the normative scenario
in five cases against installed Nexus, Core and Connector artifacts:

1. An embedded runtime and an automatic remote Connector runtime are both READY
   for the same subject and logical workspace. Local priority wins one message
   delivery; MCP pull is excluded and the remote native peer receives no turn.
2. The same competition with remote priority admits exactly one remote turn,
   preserves its logical delivery/consumer identity and excludes local execution
   and MCP pull. The Connector uses a real loopback WebSocket.
3. A canonical mirror-only observer receives no executable prompt or operation.
   There is no context-only action in the current wire; this is a safe refusal,
   not evidence of native context injection.
4. Native terminal success retains CLAIMED handoff state until the governed
   completion call; claim identity, epoch and replay remain stable.
5. Concurrent MCP pull and managed handoff claims yield one winner, one claim
   epoch and at most one native turn with matching execution-grant consumption.

Both combined cases close both canonical sessions and verify that no legacy
harness session was created. The existing standalone remote delivery case also
passes as a regression of the shared fixture. Total: **6 product passes and
3 architecture checks**, with no skips. No production code change was needed.

`run_ns06_05_combined.py` verifies installed wheel bytes and nonstatic Nexus
sources, then runs isolated Python outside the checkout. The Nexus wheel is the
previously verified event-view artifact. Native peers and protocol readiness are
fixture-qualified, and policy selections/current revisions are fixture setup;
this proves domain integration, not real provider qualification, public policy
reconfiguration, or final platform acceptance.

TR4-06-05 is verified at its specified domain_integration layer. NS15.03 remains
open for subscriber parity audit, cross-protocol failure fallback, canonical
capture retention and native loader removal. Full restore and release gates
remain open. This evidence does not close other NS06 requirements or M12.
