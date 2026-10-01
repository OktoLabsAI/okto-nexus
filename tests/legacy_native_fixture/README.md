# Retired native regression fixtures

These retired implementations are retained exclusively to exercise historical
Server domain behavior and persisted legacy sessions. Tests inject them
explicitly; production must never import this package. Setuptools discovers
only `src`, so neither the fixtures nor their native protocol implementations
are included in the Server wheel.

Current native execution and provider qualification belong to Connector Core.
Passing a test with these fixtures does not qualify a Core adapter or provider.
Process ownership, framing, buffers and version probes are also test-only.
Production retains inert historical capability interpretation and error types
needed by credential redaction. It contains no native process implementation.
