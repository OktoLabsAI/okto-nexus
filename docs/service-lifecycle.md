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
qualification. Connector supervisor integration has separate scoped evidence. An
installation record already present prevents an unauthorized detached fallback.

## Windows user logon integration

The Windows adapter is implemented, with isolated host tests. Actual task
registration, login/logout, crash recovery and installed-wheel campaigns remain
unqualified; see the R3 ledger before treating this as a qualified deployment.

```powershell
okto-nexus service install --user --start-at-login --home C:\absolute\nexus-home
okto-nexus service start --home C:\absolute\nexus-home --json
okto-nexus service stop --home C:\absolute\nexus-home --timeout 30 --json
okto-nexus service uninstall --user --home C:\absolute\nexus-home --json
```

Install preflights the selected configuration, drains an existing owner through
the same application lifecycle, then registers an instance-named Task Scheduler
task for the effective user SID. Install enables the logon trigger; `start`
requests immediate execution. It uses InteractiveToken and LeastPrivilege, with
the recorded environment's absolute `pythonw.exe`, isolated Python imports and
the same foreground Server entry. No second daemon process is launched. This is
a logon task, not a Windows Service; it does not provide availability before
login or after logout, or grant access to another user's credentials.

The task definition uses Core's bounded failure recovery (one-minute interval,
three retries) and disables hard termination. The host compares the OS-exported
definition fingerprint before each mutation. A missing ownership receipt or
user-edited definition conflicts; there is no forced overwrite or adoption.
Home and database launch guards serialize our callers, and a database ownership
receipt prevents another home from installing a competing task on the same DB.
Task Scheduler itself has no atomic fingerprint-conditional mutation API, so
external edits concurrent with a native call are outside that serialization.

Once installed, start routes through Task Scheduler and foreground `serve`
refuses competing supervision. The scheduled entry checks installation identity,
saved-context fingerprint and native task ownership before DB bootstrap. Status
reports native task state separately from application readiness; queued/running
does not certify that the application is ready. A persisted start intent also
prevents resubmission after a lost native response.

Stop persists a suppression latch before requesting canonical drain. It never
calls Task Scheduler's forced stop operation. During that login session, a crash
retry observes the latch and exits without admitting work. A later login is
distinguished by the effective token's logon ID and time; explicit `start` can
also resume the integration. Failure to confirm drain remains unconfirmed even
if the wrapper exits successfully to suppress retries. Stop during queued startup
can fence the entry before any Server owner acquires the database. Login behavior
has isolated contract tests; an actual login campaign is still required.

Uninstall drains first, requires native inactivity and removes only the selected
task and its ownership/control receipts. Context, database, projects, credentials
and shutdown evidence remain. A repeated uninstall can recover a lost removal
response by positively observing task absence. Installation failures preserve an
`installing` receipt; positive absence permits retry, and a persisted native
response permits completion without registering again. If the creation response
was lost before its native fingerprint was saved, the existing task is retained
for explicit review in Task Scheduler. After removing that reviewed task, repeat
uninstall to clear the receipt, then install again. Edited definitions can instead
be compared/restored against `native_xml` in `service-installation.json`.

The wrapper retains a coded supervisor exit record and the canonical drain
receipt. The foreground Server also emits the bounded lifecycle log described
below. Enable/disable/reconciliation UX, upgrade workflows and other-platform
adapters remain open R3 requirements.

## Passive service logs

```powershell
okto-nexus service logs --home C:\absolute\nexus-home --tail 50
okto-nexus service logs --home C:\absolute\nexus-home --follow --json
```

The foreground, detached and scheduled Server paths share `logs/service.jsonl`
under the selected home. The runtime opens it only after instance exclusion.
Records carry timestamp, generation, supervisor, lifecycle code, state and a
known error code. They cover startup, local query readiness, bootstrap failure,
reported shutdown and process exit. They contain no provider messages, prompts,
exception text, credentials or URLs. Existing task/session results and recovery
records remain canonical; this log cannot establish completion of work.

The active file rotates at 2 MiB with three backups. `--tail` accepts 1..10000
records within a 256 KiB read budget; truncation is explicit. The view reads the
active file and withholds malformed/unknown records. `--follow` closes each read
handle before polling again, resumes after append/rotation, and reports observed
rotation. A slow reader can miss records moved into backups; this is a bounded
diagnostic view, not a complete event journal. JSON follow emits one JSON object
per nonempty/changed observation. Ctrl+C exits 130 and only ends observation.

Logs never bootstrap, start, inspect the transport or ask the native supervisor
to run. An absent home remains absent. Reading logs still works if the retained
Python context is broken. Missing logs return `LOG_NOT_FOUND` with exit 0;
inaccessible/redirected logs return `LOG_UNAVAILABLE` with exit 3. Neither case
means stopped, idle or free of uncertain work. General operational/runtime
diagnostics continue to use their existing canonical surfaces.
