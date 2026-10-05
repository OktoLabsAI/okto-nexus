# NS14.04 bounded positive authentication cache

## Implemented behavior

AgentKeyAuthService previously retained every positive key lookup indefinitely unless that key was queried after expiry or explicitly invalidated. TTL alone did not bound retained entries. The cache now uses least-recently-used eviction with a maximum of 4096 entries, matching the planning limit. Both the hash cache and agent reverse index are evicted together. A caller may lower the capacity or disable caching; values above 4096 are refused. TTL is constrained to 0–60 seconds, including rejection of nonfinite values.

A short reentrant lock protects cache/index changes. Repository I/O runs outside that lock. Synchronous agent/all invalidation advances a cache generation so a lookup that was already in flight cannot repopulate the cache from its older transaction. Negative lookups remain uncached. Key rotation, revocation and last-seen writes preserve the existing service contract.

The generation check prevents stale cache insertion; it does not claim to revoke a request whose identity was already resolved before invalidation, or replace durable execution authorization epochs.

## Tests and measurement

Directed cases cover LRU behavior, reverse-index bounds, expiry, revocation, disabled caching, invalid parameters and both per-agent/global invalidation during a held repository read. The existing authentication tests cover key rotation and SQLite integration.

The load case seeds 100,000 distinct identities in a migrated SQLite database, resolves all keys through the actual service/repository and performs revocation/reactivation churn. EXPLAIN QUERY PLAN confirms an indexed key lookup. Tracemalloc samples after each 25,000 identities check that both indexes remain at 4096 and that retained memory plateaus with the fixed-size synthetic payloads. The measurement excludes initial database seeding, uses one database transaction for the lookup loop and includes Python tracing overhead. It is not an HTTP throughput or physical-runtime concurrency claim.

The installed runner compares all three packages against their source and recorded wheels, then tests authentication, agent keys/connections, HTTP API, import boundaries and R4 lease/local realization integration. Exact commands, results, hardware and measurements are in test_runs_20261001_auth_cache.json.

## Initial broader regression findings

The first installed campaign had 97 passing cases, two failures and one setup error. The migration fixture had a fixed schema-82 endpoint although the shipped package has later migrations; it now checks the complete shipped migration sequence while retaining identity and foreign-key assertions. The MCP self-connect fixture still launched removed stdio transport; it now uses the MCP SDK over the fixture's real HTTP socket and verifies one opening and idempotent reuse.

The general authentication HTTP fixture invoked provider discovery by default and one startup lost inventory ownership. It now explicitly disables harness integrations and embeddings for that authentication-only surface. The initial raw evidence is retained. This isolation does not qualify or resolve the separate real-provider startup ownership failure; startup qualification remains part of the existing M05/M11 acceptance scope.

## Remaining NS14.04 scope

This increment does not close NS14.04 or TR4-14-04. The normative combined flood/control test, item-and-byte queue quotas, fair scheduling across executors, critical control reserves and aggregate metrics still require their own implementation review and acceptance. Entry bounds do not establish a byte limit for arbitrary agent metadata. All release gates remain open. The Core and Connector artifacts remain unchanged; preexisting UI assets retain their previous acceptance status.
