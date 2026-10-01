# NS14.04 atomic pending admission capacity

## Product changes

Each executor now has independent pending admission budgets: 32 productive operations with 2 MiB of semantic bytes, and 8 control operations with 512 KiB. These byte budgets derive from the planning 64 KiB inline limit multiplied by each lane's item limit. Counts include ACCEPTED, DISPATCH_PENDING and RECONCILING operations, including initial-turn children that do not yet have an outbox row. A durable dispatch acknowledgement or terminal resolution leaves the pending set; elapsed time does not.

All three operation producers check capacity inside their existing write transaction: canonical operation submission, initial-turn child admission and native approval/input decisions. Replayed operation/decision IDs bypass a new charge. If an opening fits but its initial child does not, the whole admission rolls back, including the session and outbox. Native input is retained in memory only after the quota check.

Migration 091 adds admission_bytes to the operation row, so the durable operation ID owns its charge. New rows store the exact serialized semantic cost; native input decisions charge the reconstructed wire semantic without persisting the answer. Historical input-reference rows receive a conservative additional 16 KiB because their exact response bytes may be unavailable. Other historical rows use their stored UTF-8 length. IDs, payloads and outcomes are preserved. The lookup also protects older/manual rows from undercharging their stored payload and uses a partial executor/action index. It materializes at most the lane's item limit, independently of historical operation count.

Public operation and native-decision quota refusals return HTTP 429, Cache-Control: no-store and Retry-After: 1. They do not admit a new operation or claim a native effect. Read/replay remains available.

## Tests

The directed public tests cover 32 accepted turns plus a refused 33rd, eight independently accepted closes plus a refused ninth, replay under saturation, no native sends while dispatch is stopped, byte refusal before session/operation creation, parent/child rollback, and atomic native approval/input refusal. Two requests race for the final slot; exactly one is admitted, its replay succeeds, and a durable acknowledgement permits the previously refused intent to be retried with the same IDs.

The migration case executes shipped SQL with UTF-8 and input-reference rows, checks preserved IDs/costs, rejects negative costs and verifies the pending index query plan. A legacy schema-64 upgrade and second idempotent migration run are included in installed regression. This is not the complete M12 migration/cutover acceptance.

The installed runner compares source, wheel and installation bytes for all three products and runs Connector execution/admission plus Nexus capacity, initial-turn recovery, native decisions, reuse, migration and import boundaries. See test_runs_20261001_admission_capacity.json for results and artifact hashes.

## Remaining acceptance

NS14.04 remains partial. The normative combined 100k-identity/flood/control measurement, executor fairness under sustained load, aggregate metrics and the broader milestone dependencies remain open. These pending admission limits do not replace Core physical runtime or journal quotas. Core and Connector artifacts remain unchanged. Preexisting UI assets retain their prior acceptance scope; no release gate is closed.
