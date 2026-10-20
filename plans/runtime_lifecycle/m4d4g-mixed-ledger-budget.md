# M4d4g: mixed Core ledger capacity budget

Core commit `9b84aa4` measured one physical journal registration and one
terminal, effect-free `new_session` capacity reservation per retained session.
The 100,000-pair ledger allocated 256,573,440 bytes: 44,011,520 for the
registry and a further 212,561,920 for capacity history. The former Core
default of 64 MiB would be exhausted; Core now uses a 512 MiB SQLite growth
ceiling by default. The ceiling does not preallocate disk space.

Core passed 15 focused source and 15 installed-wheel tests. Nexus vendors the
same Core 0.0.12 wheel, SHA-256
`55b58a13f7112e63a44a08efb787ca5e43128f4d090fd639a7a9b307e5e43ecd`;
its vendor manifest check passed. Connector vendors the identical wheel and
both clean packaging/installation tests passed. The dependency pins remain
Core 0.0.12 in both consumers. The full measurement method and limits are in
Core's `plans/runtime-lifecycle-m4d4g-mixed-capacity.md`.

This is a bounded budget correction for the measured history profile, not a
retention policy. Maximum-size identifiers, longer histories, real-host load
and stream fairness remain unqualified. The global Nexus stayed stopped, so
M4's real UI gate and controlled rollout are still pending.
