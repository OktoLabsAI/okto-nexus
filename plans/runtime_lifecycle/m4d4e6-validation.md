# M4d4e6: bounded forward-head prefix verification

Core has a resumable sparse digest index, allowing an exact historical
registry digest to be computed from at most 128 rows. Nexus and Connector
convert that index in retained background tasks and compare the old host
digest before staging any newer token. A deliberately divergent prefix is
refused without changing the stored token. Neither host skips its physical
startup audit or claims readiness from this evidence.

Final installed wheels passed 26 Core registry/cost cases, 7 focused Nexus
binding/import cases and 11 Connector binding cases. Core's historical digest
read used 1,108, 228 and 388 SQLite VM steps at 1k, 10k and 100k records.
Wheel SHA-256 values: Core
`f24687913600dfbdfa85cf5c04f7106adca0a4b6903f5981f6e783e7fe200038`,
Nexus `75ac4d547a620013483d91f84268b51542a2fb0bf34b72b0b8ac6fd27d5d0f06`,
Connector `de7e9f695bc8dc7a672fb33ace5eb79789f575c5f6dd2fb03ee5743ebe92e1ca`.

The global generation 73 was untouched. Directory anomaly policy, the
unverified interval before a background audit finishes, the combined mixed
capacity budget and a real UI milestone gate are still pending.
