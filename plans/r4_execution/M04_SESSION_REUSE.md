# Canonical session reuse

## Delivered behavior

Nexus 2ac9b1c and Connector 8dbd92f add automatic and explicit existing-session selection. Core 9c77871 / 0.2.44.dev0 is unchanged.

Automatic start creates an opening only when the binding has no live claim. Exactly one compatible READY session can be reused after canonical identity, policy, grant, applied lease, connection generation, realization and fresh inventory checks. Explicit new-session always requests a distinct claim. Multiple live claims require explicit selection. Unresolved or incompatible claims are refused.

Resolution records a new client intent referring to the original opening operation. Confirmation revalidates authority inside the writer transaction and records its timestamp without another operation, dispatch or native call. Repeated confirmation recovers the original history. Original provenance lookups exclude reuse aliases. Concurrent automatic resolutions cannot both admit an opening.

Connector start accepts automatic selection and --session-id. The response exposes reused and retains the opening's original client_intent_id. Operation identity, semantic hash, action and scope remain validated.

## Migration and verification

Migration 089 adds session_selection and reuse_admitted_at. Existing rows default to explicit and retain their prior contents. The installed upgrade test covers 088 to 089 and repeated application.

Installed tests: 76 Connector, 82 Nexus, one upgrade case. Source runs overlap these suites and are not additive coverage. The HTTP/WSS public CLI journey reuses a session before continuing the existing five-action journey with only one native opening. Authority fault cases cover resolution and confirmation separately.

The campaign also reproduced a preexisting wrong-agent realization response of 422 on the baseline wheel. It now returns permission-denied 403. Earlier failure reports remain in the evidence index.

[Artifact hashes, commands and results](test_runs_20261001_session_reuse.json).

## Remaining fixed-plan acceptance

Initial start text still requires a separate turn. A durable child turn released only after READY is not delivered by this increment. NS05.04 and M03/M04 remain open. Complete process/ownership views, logs, retention and UI acceptance remain pending.

Tests use a synthetic native peer and readiness fixtures. Historical real-provider campaigns are not acceptance of these newer consumer wheels. No release gate closes.
