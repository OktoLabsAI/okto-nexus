# NS14.04 fixed-cardinality local capacity gauges

The existing GET /api/v1/metrics/local/summary surface now adds runtime_capacity and authentication_cache for operators. Other authenticated agents retain the previous telemetry summary without the new global runtime gauges.

runtime_capacity reports pending-admission item/byte totals and held dispatch item/byte totals, each with the fixed regular/control categories. Pending limits are explicitly labeled per executor; the gauges are installation totals and may exceed one executor's limit. RECONCILING work remains visible until durable acknowledgement or resolution changes its state. No agent, session, executor, connection, operation or credential becomes a metric label or appears in these projections.

authentication_cache reports occupied entries, configured capacity and TTL under the cache lock. Entries are retained cache entries, including expired entries awaiting lookup or LRU eviction; the gauge is not an active-agent count. Neither gauge creates per-agent timers, threads or persistent measurement rows.

Runtime SQL failure returns status unavailable rather than zero backlog. Operator responses use Cache-Control: no-store. These measurements remain local response data: they are not added to anonymous-beacon payloads or emitted as telemetry events.

## Verification

Three directed cases cover known pending/reserved costs, an uncertain reservation followed by durable resolution, operator/nonoperator visibility, absence of IDs/credentials in the new fields, and unavailable storage. The installed runner also verifies admission/dispatch capacity, telemetry, authentication/cache behavior, the 100k-identity cache workload and import boundaries. Source, wheel and installation bytes of all three products are compared before tests. Results and hashes are recorded in test_runs_20261001_capacity_metrics.json.

## Remaining scope

This increment supplies the aggregate gauges required for measurement. It does not qualify the combined normative TR4-14-04 load test or sustained fairness across executors. NS14.04 and its broader milestone dependencies remain partial, and all release gates remain open. Core/Connector artifacts are unchanged. Existing provider and UI evidence retains its recorded scope.
