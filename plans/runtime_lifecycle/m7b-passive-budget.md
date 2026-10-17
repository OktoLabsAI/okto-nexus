# M7b: passive Pi identity reader budget

Core commit `ab87980` limits Pi's periodic passive identity scan to two file
readers. An admitted opening still uses four. The complete dependency closure
is hashed in both cases; no completed identity is cached and the pre-spawn
authority/content check is unchanged. This reduces the scan's concurrency
budget, not the amount of verification. The real local Pi installation has
about 14,097 closure entries; previous read-only profiling measured a full
identity at 13.185 seconds under the former four-reader setting.

The selected Core source campaign passed 100 tests, including identical
identity output, reader budgets, cooperative cancellation and runtime open.
The same 100 passed from a separate environment importing the built wheel
from its `site-packages`. Nexus and Connector vendor that same Core 0.0.12
wheel, SHA-256
`d9cf577731e123c417eb731c6b34b5e6fa208be7f33d86441e426c8fedadc1e8`.
Nexus's vendor manifest carries this digest. Both projects retain their
existing Core 0.0.12 dependency pins.
The Connector packaging campaign built and installed its wheel in a clean
environment with the vendored Core wheel; both packaging tests passed. The
Nexus NS01 vendor check passed and the manifest hashes were rechecked.

This is an M7 technical checkpoint, not UI-B completion. The shared Windows
host was under heavy load from an unrelated project during diagnosis; no
before/after latency or CPU improvement is claimed. The global Nexus was
stopped at the operator's request and remains stopped. A future major UI gate
must qualify the installed combined build with real harnesses, load and
recovery before this work is deployed globally.
