# M8 final pre-wheel backup — 2026-10-20

Before replacing the global Nexus wheel, port 8202 had no listener and the
Nexus process audit found no running Server. The read-only database check
reported schema 152, seven agents, 336 messages, 348 deliveries, six handoffs,
three artifacts, and zero foreign-key violations.

The installed offline backup procedure created
`build/m8-global-final-full-backup-20261020` from
`C:\Users\jpamb\.okto_nexus` without starting native processes. An independent
`validate` invocation passed. Its private version-2 manifest covers 434 files
and 250,005,763 bytes, including the database, journals, artifacts, and
Server-owned session configuration. The manifest's database counts match the
read-only check. The snapshot remains outside version control.

This is a reversible pre-install checkpoint. It does not qualify the new wheel
or prove the post-install UI behavior.
