# NS06.05 canonical consumption evidence — October 1, 2026

The installed Nexus/Core/Connector artifacts now have direct evidence for the
existing canonical inbox exclusion contract. No production change was needed:

- MCP inbox pull cannot consume an embedded canonical push reservation before
  dispatch, after native acceptance, or after runtime close. Repeated pull
  leaves the consumer, operation identity and attempt budget unchanged.
- Pull handoff claim and managed canonical handoff claim compete for one claim
  epoch. Both sequential orders and concurrent public MCP requests yield one
  winner, at most one canonical turn, and matching execution grant consumption.
- Public MCP message creation reaches the automatic Connector daemon over a
  real loopback WebSocket and Core native fixture. MCP pull cannot consume its
  reserved delivery. The remote native effect, receipt and subsequent controls
  retain the same canonical session, without legacy harness rows.

`run_ns06_05_consumption.py` verifies the existing wheel bytes against the
checkout and runs outside the checkout with Python isolation. Seven product
tests and three architecture checks pass. The wheel is the previously verified
event-view artifact; no product code changed in this increment.

Remote setup explicitly acknowledges the current configuration revision after
its fixture-only policy selection. An earlier stale fixture revision correctly
caused ATTACH_DENIED. This does not prove a public reconfiguration workflow.
Native peers/readiness remain synthetic; this is not provider qualification.

The combined local/remote endpoint competition on one logical delivery remains
pending. The existing observer test proves refusal of executable prompts; the
current Core wire offers no context-only action. Do not invent a turn to deliver
observer context. Native terminal versus governed handoff completion has separate
evidence in M12_NS15_03_HANDOFF.md. Normative TR4-06-05 remains open until the
combined scenario is covered; NS15.03 and final release acceptance remain open.
