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
does not authorize replay or clear uncertain work. This change does not yet add
automatic start, an OS service, or new readiness/control commands; those remain
the next R3 lifecycle increments.
