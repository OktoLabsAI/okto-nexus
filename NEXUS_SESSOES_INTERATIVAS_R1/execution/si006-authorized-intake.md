# SI-006 authorized intake

The internal intake service holds the login fence and the execution writer
through the durable receipt. It checks the exact executor, workspace,
binding, session and owner generation. It confirms the existing applied
lease, connection authority and represented agent's grant. The check
consumes no grant budget. Migration 170 keeps the original grant ID and
revision alongside the human authority reference for later revalidation.

An exact retry by the same current login recovers its stored result. A
new intent must match the capability revision supplied by the trusted
Server projection. The authority check is independent of transcript
history and does not resolve an R4 intent or introduce an outbox entry.
Applied-lease and subject-grant checks are shared with the existing R4
send gate. Its consumption and containment behavior are preserved.

The combined NS-09, dispatch-pump, canonical-fairness and interaction
regression passed 55 tests in the isolated prefix. The R4 integration
fixture exercises a real SQLite grant and the canonical applied lease
through a synthetic runtime, together with a temporary operator login.
The check covered stale generation and capability, exact retry, original
grant retention, no new R4 rows or budget consumption, and refusal after
logout. The capability value was supplied by the fixture. There is no
public endpoint or qualified Server capability projection for this
service yet. No provider was called.

Migration 170 adds nullable provenance fields without rewriting the
existing receipt. They may remain when returning to the previous binary.
The feature path stays closed until a later stage can revalidate the same
grant at the shared send gate and safely reconcile an in-flight operation.
