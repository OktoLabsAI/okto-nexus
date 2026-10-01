# Retired native regression fixtures

These four implementations are retained exclusively to exercise historical
Server domain behavior and persisted legacy sessions. Tests inject them
explicitly; production must never import this package. Setuptools discovers
only `src`, so neither the fixtures nor their native protocol implementations
are included in the Server wheel.

Current native execution and provider qualification belong to Connector Core.
Passing a test with these fixtures does not qualify a Core adapter or provider.
The shared Server helpers still imported here also support legacy history,
redaction or compatibility and are not removed by this relocation.
