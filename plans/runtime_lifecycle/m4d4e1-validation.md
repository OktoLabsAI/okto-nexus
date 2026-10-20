# M4d4e1 installed Core registry-head qualification

Core commit `1d38900` on `feature/v0.0.12` adds a transactional physical
registry hash-chain head. The wheel installed into the disposable Nexus
environment is SHA-256
`2117495f1dd913634854116b557734ce96da081317a89149c5d6f8faf43a5090`.
The global Nexus generation 73 was not changed.

Core source and installed registry/cost suites each passed 21 cases. They
covered first registration, idempotency, conflicting-batch rollback, immutable
rows, missing-row detection, interrupted legacy conversion and 1k/10k/100k
registrations. Installed registry-head reads consumed 35 SQLite VM steps at
each size. Another 43 installed slot/capacity cases passed.

Nexus composition with this installed Core passed 27 selected cases for
physical-store binding, retained registry import, reset and catalog cost with
1k/10k historical sessions. The 100k Nexus catalog case was independently
verified on the previous Core wheel and is not claimed here as a combined
Core/Nexus result. The separate installed Core 100k cost case passed.

The registry head is not yet an audit frontier: hosts do not record an
independent nonce/digest binding and still run the physical startup audit. Real
UI and global rollout belong to a later major milestone.
