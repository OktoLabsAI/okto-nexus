# HOME-R1 canonical contract reuse

This is a focused rerun of ten existing test selectors (23 parametrized cases),
not a Home DOM, browser or real-harness qualification. No product, fixture or
test source was changed. Raw pytest XML/logs remain in the qualification's
temporary directory; the retained JSON contains only test names, outcomes,
durations, source hashes and the reviewed fixture boundaries.

The native-decision fixture uses a migrated temporary database and in-process
ASGI/WebSocket TestClient. `test_ns09.setup_authority` replaces the dispatch
pump with a no-op fixture and selects a file containing synthetic peer bytes.
`test_open_bootstrap.begin` validates and constructs the dispatch frame; these
selected tests do not start a Core runtime or invoke a provider. Leases,
admission, authentication, decision CAS and SQLite transactions remain real.
Attention HTTP fixtures disable harness integrations and local candidate
discovery; the external-observation fixture is a synthetic SQLite service.

The rerun supports reuse of canonical contracts relevant to C03–C06, C08, C09
and G02: originating interlocutor scope, stale/expired/other-client refusal,
single decision and replay, concurrent decision CAS, distinction between a
recorded decision and native application, explicit sensitive-input resupply,
shared preferences independent of domain resolution, feature-off behavior,
credential rotation revalidation, and historical external completion without
productive task success.

The tests do not prove Home double-click/lost-response UX, unknown-result
navigation, a Home decision applied by a real harness, or new browser behavior.
Those levels remain separate evidence. Scenario status and acceptance are
owned by Root; this qualification does not promote them automatically.
