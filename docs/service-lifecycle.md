# Server instance ownership

The foreground command remains `okto-nexus serve`. Before opening or migrating
the database it resolves the configured home and database paths and acquires
nonblocking OS-held locks for both. Starting another Server with the same home,
or with a different home pointing to the same database, is refused. Explicitly
different homes and databases remain independent.

`nexus.serve.lock` records PID, process generation and start time for diagnostics.
Its heartbeat is not a lease: a slow or paused process never loses ownership
because a timestamp becomes old. `.serve.guard` files are stable OS lock
resources. Do not delete or replace them while an instance may be running;
unlinking a locked file can create independent lock inodes on POSIX.

Process exit releases OS exclusion, including abrupt termination. A new process
can then replace an abandoned version-2 diagnostic record. It never signals a
historical PID. Legacy records from versions without these OS locks require
positive same-host process-exit evidence. An alive, reused, inaccessible or
unknown PID remains unresolved: stop and verify the old instance before upgrading.
Do not run old and new versions concurrently against the same home/database.

The existing shutdown coordinator and runtime reconciliation still determine
whether native resources, claims and operations are released. Acquiring a lock
does not authorize replay or clear uncertain work.

## Inspect the local instance

`okto-nexus service status --json` accepts the same `--home`, `--db-path`, `--host`
and `--port` selection as `serve`. Inspection never creates a home, initializes
storage, starts a process or cancels work. Exit codes are 0 for ready/stopped,
2 for invalid configuration and 3 for other or unconfirmed service states.

Readiness is served on the existing local operator channel at
`GET /api/v1/service`. Remote peers and participant identities cannot use it.
Status correlates the canonical home/database/effective-user identity, OS-held
guards, process PID, generation and active package/protocol version. A listening
port or historical metadata alone is insufficient. HTTP liveness remains
separate. A transport failure while an owner exists is degraded, not stopped;
the command never retries by launching another process.

The response reports storage initialization and whether canonical admission
checks are required or closed. It does not promise provider login, harness
readiness, permission for a task or absence of active work. Queries remain
available during drain; inspection cannot reopen admission. Installed and active
package versions are distinct; incompatible versions require explicit action.

Automatic start, background operation, OS service installation and controls
beyond status remain subsequent R3 lifecycle increments.
