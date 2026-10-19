# M8 global pre-upgrade backup — 2026-10-19

The global Nexus was stopped before this checkpoint; ports 8202 and 8204 had
no listener, and the process audit found no Nexus Python owner or open handle
in its home. No service or native harness was started for the backup.

The installed Nexus 0.3.1 environment ran the offline backup procedure against
`C:\Users\jpamb\.okto_nexus`, writing to the ignored local directory
`build/m8-global-preupgrade-backup-20261019`. The procedure verified the
source writer lock and expired owner lease, copied under the SQLite writer
fence, and validated the snapshot before returning `PASS`. A separate
`validate` invocation also returned `PASS`.

The version-2 manifest covers 407 files and 225,503,491 bytes. Its database
is at schema 145 and records 7 agents, 325 messages, 337 deliveries, 6
handoffs and 3 artifacts. The source home has additional caches and other
non-recovery files; the procedure copies only the Server-owned database,
journals, artifacts and session MCP configuration. The backup is private and
is not committed. This is a rollback prerequisite, not an upgrade or proof
that the current product has been deployed globally.
