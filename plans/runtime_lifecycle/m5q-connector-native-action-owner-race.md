# M5q: Connector Pi native action versus owner shutdown

The isolated Connector's approved Pi runtime received a `handoff.claim` through its actual loopback JSONL ingress. The test held either capability metadata lookup (before the canonical mutation could start) or the HTTP response after the fake canonical claim recorded one effect. It then closed the Connector execution owner.

In both phases, shutdown retained the Core native-action service and its runtime while the backend task was pending. In the pre-commit phase no claim was sent after the owner closed; in the post-commit phase the one recorded claim was not replayed. The socket observer closed on drain, and the owner completed only after the pending task settled. This verifies local Connector retention at the native-action ingress. The embedded M5p case separately verifies durable Server claim/event/receipt state; this Connector fixture does not assert that durable Server state or a physical remote host.

The new two-case test and adjacent Connector lifecycle/native bridge suites passed against source and isolated installed wheels: 41/41 each. The first draft called the bridge directly and therefore bypassed the socket owner's pending-task accounting; it was replaced with a loopback ingress call before qualification. No production code or global Nexus process changed.

Remaining M5 scope: managed-adapter/per-binding containment and embedded/Connector differential reconnect, revocation and preserve-agents reset. The broader M7/UI-B load distribution remains separate.
