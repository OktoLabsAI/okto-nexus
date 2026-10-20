# M5c — Discovery failure before the initial lease

M5b isolates failures after the initial lease is installed. A local Connector test across Codex, Pi and Claude also showed that candidate discovery can fail before runtime construction while a sibling session is healthy. The host can prove there is no native session yet and can persist a Core `PREPARATION_FAILED` fact, but the Server rejects that receipt: the dispatch outbox has no correlated applied lease at this cut. The existing receipt endpoint authenticates a binding-scoped ticket, not the live control connection as a proof of this particular refusal.

An exploratory change allowing `PREPARATION_FAILED` without `applied_at` passed the Connector unit scenario but failed the Server prelease test. Inspection showed no outbox-to-lease join before application. Letting a ticket-bearing publisher bypass that check would weaken the opening's authority boundary, so all exploratory source and test changes were reverted; both repositories are back to their previously qualified M5b implementation.

Implement this as an in-band, current-connection startup-refusal transaction:

1. The Connector must persist the exact original operation association and Core no-effect journal fact, prove no native claim or process, and release only the matching physical reservation. A failure or uncertain observation retains that reservation and producer for reconciliation.
2. The authenticated control channel must carry a typed refusal report for the exact sent operation, connection generation, session owner generation and original binding. It must not be accepted by the generic receipt ticket endpoint alone.
3. The Server must validate current channel ownership, unchanged operation scope/intent, pending session, absence of event ingress and applied lease, and exact capacity proof in one transaction before closing that session and publishing the terminal caller error. Duplicate reports are idempotent; stale/foreign reports fail.
4. Only after that server acceptance may the Connector drop the producer. A lost acknowledgement replays the same durable report; an uncertain native effect follows normal reconciliation rather than this no-effect path.

Acceptance needs a separate-process Connector test: fail first candidate discovery, observe one terminal caller error and exact capacity release, then submit another handoff through the same control connection while a healthy sibling continues. Add forged ticket, wrong generation, lost acknowledgement and crash-cut cases. This checkpoint does not establish M5 completion and changes nothing in the running global installation.
