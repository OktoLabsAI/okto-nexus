# NS15.03 physical helper removal and normative acceptance

The remaining legacy native process implementations (Windows Job Objects,
Linux guardians and the owned-process wrapper), protocol framing, transient
event buffers and version probes are removed from the Server package. Historical
regression fixtures retain them outside `src`. Production compatibility is now
only interpretation of stored reports; diagnostic redaction retains four inert
error types without importing process or protocol implementations.

TR4-15-03 has a normative entry in `test_ns15.py`, with REST and MCP cases.
It inspects the actual package under test, rejects application-Connector and
test-fixture imports, rejects subprocess/socket/ctypes in the legacy harness
package, and verifies that all ten retired modules are undiscoverable in an
isolated process. The same cases exercise existing public Core dispatch,
idempotency, durable operation history and closed-session reads. The installed
wheel additionally excludes the retired modules and all test-only fixtures.

The targeted regression campaign covers process birth/termination, protocol
limits, fragmented pipes, bounded buffers, error redaction, compatibility and
serve/restart behavior. Generated owner scripts now include the explicit test
fixture directory. No production import shim, native factory or fallback was
introduced. Test peers and readiness qualification remain synthetic; Windows
results do not qualify Linux or real providers. Historical relay subprocesses
use checkout source verified byte-identical to the wheel.

The canonical retry contract remains scoped reconciliation before new work;
`retry_safe=false` is not authority for automatic cross-binding transfer. The
existing typed legacy pre-write proof still permits approved legacy-to-R4
fallback. NS15.03 removal adds no new retry policy or validation target.

Task dependency acceptance and final release gates remain open. The next M12
requirement is NS15.04 configuration migration and safe restore after effects.
Evidence: `run_ns15_03_helper_removal.py`, the installed manifest/logs/XML under
`evidence/ns15-03-helper-removal-*`, and
`test_runs_20261001_ns15_03_helper_removal.json`.
