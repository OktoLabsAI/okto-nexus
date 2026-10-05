# Bounded embedded shutdown observation and retained recovery

Nexus 4a7023b; unchanged Core c2aed11 / 0.2.49.dev0 and Connector dca0863.

## Implemented

EmbeddedDispatchOwner.request_shutdown fixes one monotonic deadline for all of its resources. The default budget is 50 seconds; it assigns up to 30 seconds to drain and 15 seconds to interruption, retaining report time. A later request cannot extend the initial deadline. The bounded wait never cancels cleanup.

The report identifies retained executor/session resources and reports DRAINING_PENDING until cleanup and resource release are proved. Its ownership projection is conservative: retained resources are reported unknown without waiting for a database or native probe. shutdown_status is an in-memory owner read.

A retained recovery task joins each cleanup pass, then retries only finished uncertain or failed passes. It preserves the runtime host, journals and native owners. A failed containment task is replaced only after it has finished; recovery after the deadline uses zero additional drain/interrupt budget. Successful recovery changes the state to DRAINED. Canceling a request observer does not cancel cleanup or recovery.

The Nexus lifespan requests the bounded report and then awaits retained recovery before closing inventory, releasing the serve lock or disposing the owning loop. The report is available on app.state.embedded_shutdown_report. Pending recovery does not authorize a process exit.

## Tests

The focused cases exercise two sessions with blocked quiesce, outbox stop or historical reads, fixed deadlines across repeated requests, observer cancellation, uncertain native close, containment exception, and actual lifespan ownership retention followed by backend restoration.

The first uncertain-result test exposed that a single immediate retry does not await the Core's retained cleanup producer. That failure remains recorded. The implementation now owns a recovery loop, and the corrected case observes completion through wait_shutdown.

A separate failing test reproduced a failed initialization remaining in the host's resource map after its journal had already closed. The host now records successful initialization cleanup and removes only those proved-released failed entries. A cleanup without that proof remains retained.

## Installed evidence

The broad candidate passed 106 Nexus and four legacy shutdown cases. After the failed-composition correction, the final wheel passed 14 directed shutdown/host cases and the same four legacy cases. Source/wheel/installed bytes matched, and pip check passed. These results overlap and are tied to separate hashes in the [manifest](test_runs_20261001_shutdown_deadline.json); they are not a full final release regression.

## Remaining NS14.03 requirements

This is the embedded owner/lifespan implementation. It does not complete the Server-wide public CLI/HTTP shutdown contract: a serving administrative recovery endpoint, one budget across all Server owners, and in-memory admission fencing across all entry points remain required. Uvicorn's normal transport shutdown precedes ASGI lifespan cleanup, so app.state availability alone is not proof of a reachable administrative service.

The report still needs qualified distinction between unknown process state and durable-release-only pending state. The late-open, blocked durable release and full platform matrix remain required. No release gate closes with this increment.
