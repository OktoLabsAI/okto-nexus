# Runtime handoff notifications

Creating a directed handoff notifies its eligible runtime recipient. Creating a
broadcast or pool handoff notifies eligible agents with an approved, enabled
conversation runtime connection in the handoff workspace. The creator is not
notified about its own handoff.

Notifications contain the handoff ID, availability metadata, and instructions to
claim it through Nexus. They do not include the work payload and do not claim the
handoff automatically. Normal claim permissions and first-claim-wins semantics
still apply. A blocked handoff is marked as blocked; an additional notification
is sent when its dependencies are satisfied.

Notifications enter a durable delivery queue in the handoff transaction. The
dispatcher rechecks the handoff state, recipient eligibility, communication
scope, and runtime authority before dispatch. Cancelled handoffs and recipients
that are no longer eligible cannot trigger execution. Existing MCP inbox and
claim behavior is unchanged. Runtime notification delivery is independent of
the global automatic session recovery setting.

This uses the existing runtime delivery infrastructure for both local and
Connector-hosted runtimes; it does not add a separate Connector event protocol.
