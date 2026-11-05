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

## Start, stop and reopen

```sh
okto-nexus service start --home /absolute/nexus-home --host 127.0.0.1 --port 8202
okto-nexus service status --home /absolute/nexus-home --json
okto-nexus service stop --home /absolute/nexus-home --timeout 30 --json
okto-nexus service restart --home /absolute/nexus-home --timeout 30 --json
```

Start saves resolved configuration, interpreter/venv and working-directory
references in `service-context.json`. Later commands select the same context by
home without repeating the port or settings. It records only an allowlist of
environment references and absolute PATH directories. Provider keys and arbitrary
shell environment are not copied: credentials must be available through the
existing user login/vault. A deleted interpreter or working directory is an
explicit configuration failure. Projects still retain their own runtime paths.

A short-lived launch lock and durable receipt serialize concurrent callers.
The child validates its launch token and takes Server ownership before entering
the existing foreground implementation. Windows uses detached process/new group
with job breakaway; POSIX uses a new session. Streams are disconnected from the
launching terminal. A ready compatible owner is reused. A stopping, incompatible
or unidentified owner is never replaced. A timeout leaves the launch intact;
use status to observe it. An interrupted pre-spawn receipt with no confirmed
child remains unresolved instead of silently creating another launch.

Stop names the observed instance/generation and calls the existing shutdown
coordinator through the local operator HTTP adapter. It affects every project
sharing that Server. Participant keys, remote peers and cross-origin requests
cannot stop it. It never signals a cached PID, kills on timeout or cancels a drain
to satisfy a concurrent start. A correlated shutdown receipt distinguishes
confirmed drain from an unconfirmed process disappearance. Restart requires
confirmed stop; it cannot convert a pending drain into a new process.

Exit 0 means the requested start/restart reached ready or stop was confirmed.
Exit 3 preserves pending/degraded/uncertain outcomes in JSON, including canonical
shutdown resources where available. A CLI wait timeout is not task cancellation.

This detached mode has no crash restart policy and does not promise survival of
logout/reboot. Actual Windows child tests prove survival of launcher exit;
closing a real terminal and installed user-service campaigns remain separate
qualification. OS service registration, installed-supervisor routing, logs and
Connector lifecycle integration are subsequent R3 increments. An installation
record already present prevents an unauthorized detached fallback.
