# Physical stop and durable release in shutdown reports

## Shared Core contract

Core 0.2.50.dev0 adds the public synchronous `shutdown_resources()` query to RuntimeCore. Call it on the runtime's owning event loop. It copies retained SessionKey facts without storage calls, native probes or mutations. The returned mappings are detached from runtime state.

- `process_state=STOPPED` requires a previously observed native stop. An unfinished opening, running resource or unproven stop remains UNKNOWN.
- `release_pending=true` means a durable owned-slot obligation remains unconfirmed. Physical STOPPED does not imply successful durable release.
- Shutdown tombstones are created after observed stop; they preserve STOPPED while distinguishing released versus uncertain ownership.
- The query does not authorize store closure, transfer ownership, grant a new opening or synthesize successful close receipts. Existing shutdown outcomes and retained producers remain authoritative for disposal.

The stop marker is recorded before awaiting release in both normal close and independent containment. No close/force sequencing is changed by this increment.

The recovery test also exposed a preexisting stale tombstone: an expired resource could be stopped and evicted with release pending, then retain that pending marker after the ledger confirmed release. Consuming a successful release producer now clears the matching live binding's reserved-slot flag and updates an existing tombstone to released. The original opening operation must match before a live binding is updated. Failed producers leave the obligation intact. The failing test and candidate artifact results are preserved separately from the corrected final wheel.

## Nexus integration

EmbeddedRuntimeHost reads the public Core query for each retained runtime. The administrative shutdown resource report now includes `process_state` and `core_release_pending` alongside `outcome` and `store_retained`. STOPPED with core_release_pending=true distinguishes a confirmed native stop with pending owned-slot release from UNKNOWN native state. A retained host journal can still have store_retained=true after Core release is confirmed.

The report remains conservative for unfinished/failed composition. Legacy supervisor resources retain their separately labeled legacy reporting; this increment qualifies the Core-backed embedded path.

## Tests and artifacts

Core tests hold or fail durable release after native stop, read the public facts without waiting for storage, verify caller mutations cannot affect the runtime and recover the same resource after release becomes available.

An additional expiry/eviction test proves that later successful release changes both the diagnostic fact and the next public shutdown outcome to already_closed, without reopening the native session.

The public Nexus test starts two runtimes: one stops while its durable release is blocked; the other reports unknown close and remains unproven. Operator HTTP reports both distinct states within the same pending shutdown. Health stays available, the same runtime instances are retained, and restoring both backends drains them without another opening.

Nexus and Connector pin the identical Core wheel. See test_runs_20261001_shutdown_facts.json for installed results, exact artifacts and commits. Source cases overlap installed coverage. Older actual-provider evidence keeps its original tuple.

## Remaining acceptance

The combined late-open/stuck-close/independent-force matrix through the public Server entry point, external console/Linux signal qualification, authorization-store outage, explicit force-exit qualification and platform/provider acceptance remain pending. NS14.03 and release gates remain open. UI assets included in the wheel are not accepted by this campaign.
