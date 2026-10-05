# NS15.03 canonical connection discovery — October 1, 2026

Existing connection settings, self discovery and binding discovery now recognize
canonical R4 endpoints through the public Core catalog. Operator configuration
accepts Core adapter IDs, preserves optimistic policy revisions and revokes the
method's connection keys when disabled. R4 endpoint settings no longer ask the
legacy native registry for a descriptor or use the Server platform as the remote
executor's platform authority.

REST `/api/v1/connections/available` and MCP `harness_list` with connections
`available` share the same service, owner freshness map and protocol gate. A
canonical connect action is offered only with current endpoint authority, one
approved binding, ready executor/workspace/realization, matching fresh inventory
and current candidate evidence. These are read-only observations; discovery does
not resolve an intent, persist an operation or probe a provider. Admission and
dispatch revalidate authority when the returned action is actually called.

The returned placeholder key must be replaced before opening. Canonical opening
now rejects the discovery placeholder just as the legacy self-connect path did.
The bindings view reads canonical session history and Core descriptor metadata;
durable lifecycle fields do not assert process liveness or effective capabilities.
No private paths, realization records or credentials are included in these views.

Directed public tests cover following the advertised MCP action through one
opening across retries, placeholder refusal, operator configuration and key
revocation, stale policy revision, caller denial, grant/inventory/executor/protocol
blockers and canonical binding history. The installed campaign includes the
existing legacy HTTP/MCP connection, self-connection, discovery and grant suites,
plus canonical opening, keys, dispatch and local realization regressions.

Installed results: 76 R4 and 51 legacy cases passed in the initial campaign.
One legacy test still started removed MCP stdio. It now uses the actual MCP HTTP
client and retains the same authenticated equality assertion against the REST
projection. That corrected case and three architecture checks passed on the same
installed wheel, giving 128 distinct product-test passes plus three architecture
checks. The initial failure is retained; no product code changed after the build.

Core and Connector artifacts and database schema are unchanged. Native peers are
synthetic and readiness qualification is fixture-local. This is not provider
qualification or normative TR4-15-03 acceptance. Implicit endpoint selection,
boot, delivery and event projection still require cutover before removal of the
duplicate native loaders/codecs; domain and historical recovery remain present.
