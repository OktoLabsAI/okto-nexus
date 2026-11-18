# J04 attempt1 — incomplete, no retry

The first two functional GETs returned200. The third returned422 because the prepared worker supplied quick=all to the legacy results endpoint, which deliberately rejects unknown query parameters. The fourth GET and final pagination/materialization/productive-after assertions did not run. This is a runner-precondition failure, not a product defect.

The source1829/payload1031 guards match, original seed is unchanged, installed origins match, worker exited1 normally with no timeout/force/remaining. Only a synthetic owned clone was altered. No latency was collected. Any corrected runner requires a new immutable counterpart and Root gate.
