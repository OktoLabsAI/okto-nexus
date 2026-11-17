# Attention authority and Home-OFF browser qualification

Two isolated real-browser/HTTP cases use the original canonical native fixture,
its admitted channel/session and exact question recipient. No provider, model,
native executable or personal account was used. The browser uses the actual
trusted loopback human operator, with no bearer agent key or fixture actor
header. Canonical inventory PUT and lease renew/applied maintain the existing
owned channel; grants and native request expiry are not renewed or edited.

## T-ATTN-02: PASS within inert canonical-native boundaries

The original recipient='subject' fixture is retained unchanged. Operator opens
the global queue and the same exact question. The occurrence is
question_waiting_for_agent and allows only inspect_approval. Its real inspection
has no Send answer control. The browser then attempts the exact canonical
decision through HTTP using the original approval/CAS fields read from its
detail; the actual handler refuses 403 APPROVAL_AUTHORITY_REQUIRED with
possible_effect=false (`e31956`). This is a deliberate negative authorization
probe, not a granted answer or a forged recipient.

agent/ready.json initial_state equals agent/final-db.json state: zero decisions,
zero input.provide operations, zero matching dispatch outbox; original request
remains PENDING, and original grant/expiry/budget fields are identical. The
Server journal contains exactly that one rejected POST. Inventory maintenance
and lease-applied diagnostics have no peer failure; the thread joined.

## T-ATTN-06: PASS for the literal new-Home-OFF alternative

An already created, still pending question addressed to the human operator is
opened with the supported local preference
okto-nexus-home-operational='disabled'. Browser verifies classic home-overview
exists and operational home-follow-up does not. The basic global bell reaches
the exact existing actionable question without Advanced. Its actual canonical
Send answer returns 202, CONFIRMED / DISPATCH_PENDING / possible_effect=false
(`d28f1d`). No application by the native provider is claimed.

home-off final DB contains one decision, one input.provide operation and one
matching dispatch outbox. The same original question changes PENDING→DECIDED;
its received_at/expires_at and all grant fields are unchanged. One native
decision POST was accepted. No grant renewal, request TTL extension, SQL
liveness override, substituted recipient or native response application ran.

The interception-OFF branch is **NOT_RUN**. Generic governance approvals have a
separate interception-only flag contract; native dispatch explicitly requires
HITL in its liveness/dispatch authority. This evidence does not pretend that
turning native dispatch off still authorizes a native response.

## T-NAV-06: NOT_RUN — reduced-human-authority given unavailable

The current supported human surface is a single operator account/loopback
operator. It supplies no reduced-role human account for an advanced action.
Using an agent bearer as an operator, inventing a limited human DTO or treating
an unknown generic view URL as a product link would manufacture the given. None
was done. The native wrong-recipient 403 above is not promoted into an advanced
navigation authorization test. Existing index visibility alone proves no ACL.

## Antecedents and cleanup

One preparation run used nonexistent Scenario.decision rather than
Scenario.decision_body and exited before HTTP listening (`fc8488`); the fixture
field was corrected. The first Home-OFF probe incorrectly expected
info.features.feature_home=false (`0c6233`). /info has no such feature entry;
the extra dynamic fixture attribute was ineffective and was removed. That run
made no POST and its browser-probe source, ready and journal are retained as an antecedent. The
final case uses the actual supported browser presentation preference, not an
invented Server API gate. No product changed for either correction.

The participant's browser 56787 was not touched. Own browsers closed
(`fd534f`, `1b378e`, `581bec`); fixtures/peer/WSS/factory exited 0 (`b1e8e7`,
`b73c00`, `6580e1`). Four exact own Temp allocations, including the failed
preparation, were removed physically by cleanup.ps1. No DB, credential, cookie,
raw native event or provider data is retained. No product, ledger, Git, prefix,
proposal, package or static asset was changed.
