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
below. Reviewed environment upgrades and owned-task enablement are described
below. Unrelated external definition edits remain refused; actual native service
and other-platform qualification remain separate.

## Enable or disable the installed task

```powershell
okto-nexus service disable --user --home C:\absolute\nexus-home --json
okto-nexus service enable --user --home C:\absolute\nexus-home --json
```

These commands only change enablement of the selected owned task. They do not
start, drain or cancel a running generation. Use `service stop` for canonical
drain and `service start` for immediate execution. A queued worker checks
enablement before bootstrap. Status reports the enabled login policy separately
from any current process. Disabling remains possible when the recorded
interpreter or working directory is unavailable; enabling requires valid context.

Repeated commands recognize the confirmed state. An intent is persisted before
the native call. After a lost response, repeat the same command: a matching
enablement-only native result completes its receipt without another mutation.
The opposite transition is refused while an intent is pending. Other definition
edits, including changes to triggers or privileges, cannot be adopted through
this path. An enablement change made outside the CLI also requires review when
there is no retained matching intent. This is bounded reconciliation of our own
operation, not permission to overwrite an edited definition.

The adapter uses the documented
[RegisteredTask.Enabled property](https://learn.microsoft.com/en-us/windows/win32/taskschd/registeredtask-enabled),
with a fingerprint check immediately before mutation. Task Scheduler provides
no atomic fingerprint-conditional write against an external editor. Actual native
mutation/login qualification is tracked separately from the isolated tests.

## Drain and an explicit force decision

`service stop` closes new productive admission and waits for admitted work.
Authorized native decisions, results and reconciliation remain available during
that wait. The first request fixes the drain deadline; repeating the request
does not reset it. A timeout reports `DRAINING_PENDING`, never permission to
interrupt work or proof of release.

After inspecting the same instance and its current generation, an operator may
explicitly request containment after the drain deadline:

```powershell
okto-nexus service stop --home C:\absolute\nexus-home --timeout 30 --json
okto-nexus service status --home C:\absolute\nexus-home --json
okto-nexus service stop --home C:\absolute\nexus-home --force --expected-generation REVIEWED_GENERATION --timeout 30 --json
```

Force requires an existing expired drain and the reviewed generation. It enters
the existing owned-resource containment path; it does not mark uncertain work
complete or authorize a new generation. Unknown ownership retains recovery and
the instance lock until release is proved. Restart still requires confirmed
drain. Stop intent is persisted before supervisor shutdown so the selected task
does not interpret an explicit stop as a crash. Signals and external process
termination use their separate safety-containment path.

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

If the configured HTTP port is occupied, startup fails and the log records
`PORT_IN_USE`. An unavailable address or denied bind records `BIND_FAILED`.
The Server does not select another endpoint or database. Inspect the selected
address/port and retry explicitly after resolving the conflict; exception text
is not copied into the public lifecycle log.

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

## Recover an interrupted detached launch

If a launcher exits before its child enters bootstrap, status can retain
`STARTUP_PENDING`. A wait timeout continues observing that same launch. To revoke
it explicitly, inspect `service status --json` for `launch_recovery.receipt_revision`
and run:

```powershell
okto-nexus service recover-start --home C:\absolute\nexus-home --expected-revision REVIEWED_REVISION --json
```

This acquires the home/database launch and lifetime locks, checks the exact
receipt and instance, then marks that pending launch aborted before bootstrap.
A late child must recheck the receipt under the same launch locks and exits
without constructing the Server. No PID is killed or adopted. The operation
does not start a replacement; use `service start` explicitly afterward. A changed
receipt, installed supervisor, live/uncertain owner or already bootstrapped launch
is preserved and refused. Runtime claims, grants and uncertain operations are
not cleared by this command.

After response loss, repeat the same expected revision to confirm the recorded
result. A mismatched revision remains a conflict. Status and recovery can inspect
the retained selection even if its saved interpreter disappeared; neither rewrites
that execution context. Upgrading/rebinding a missing environment remains a
separate operation.

## Reviewed environment upgrades

`upgrade-plan` reads the selected installed Python and Core payloads and emits a
complete plan with a SHA-256 `plan_revision`. It does not drain, migrate, start or
change the service. `--output` creates a new UTF-8 file and refuses to overwrite
an existing file. The source context must already exist. Editable checkouts and
unordered/prerelease versions are not eligible targets in this protocol.

```powershell
okto-nexus service upgrade-plan --home C:\absolute\nexus-home --python C:\target\Scripts\python.exe --output C:\review\nexus-upgrade.json --json
okto-nexus service stop --home C:\absolute\nexus-home --json
okto-nexus service upgrade-apply --home C:\absolute\nexus-home --plan-file C:\review\nexus-upgrade.json --expected-revision REVIEWED_REVISION --json
okto-nexus service start --home C:\absolute\nexus-home --json
```

Review the source and target executable/prefix, package/Core versions, preserved
configuration and native task references in the plan before applying it. Keep
the source environment available through canonical stop. If CLI and daemon
versions differ, use the source version's CLI to drain the reviewed generation.
A previous stopped run needs a matching retained run marker and DRAINED report.
For a legacy source without that marker, prepare the plan while it is running,
then drain it. Unknown ownership, an unresolved launch, a newer run or uncertain
shutdown prevents application.

Application holds the instance launch and lifetime exclusions. It records the
pending plan in the context before effects, then replaces only the owned task's
execution action when installed. Trigger, principal, enablement and other task
policies remain unchanged. An externally edited task is not adopted. A task must
be inactive; no forced native stop is used. Old queued launch tokens are fenced.
The native UPDATE operation suppresses registration triggers and retains the
principal ACL. The registration description remains historical; the confirmed
receipt records the new action revision and complete native export.

If interrupted, keep the plan, old environment and retained service documents.
Repeat `upgrade-apply` with the same file/revision. Status reports
`SERVICE_UPGRADE_PENDING`; starts, foreground bootstrap and other service
mutations refuse to cross that fence. A lost native response is accepted only
when the observed definition exactly matches the retained action change.
An unrelated edit or missing receipt requires review and is preserved. If the
candidate changed after review, restore that exact installed environment before
resuming; the operation does not silently switch to a different candidate.

The completed `service-upgrade.json` keeps source/target references and reports
`migration_state: not_run_by_upgrade`. Applying never starts work or migrates
storage. Explicit target start runs the existing canonical initialization and
reconciliation. Package/interpreter fingerprints are checked again before
bootstrap to detect an environment changed in place. Binary downgrade is refused;
retaining the old environment is not proof that rollback is safe after migrations.

Qualification: detached replacement is exercised with installed wheels in two
disposable Windows environments. Native update response-loss/recovery tests use
injected Task Scheduler effects; actual native task update, logout/reboot,
productive workloads, mixed historical release migration and POSIX campaigns
remain separately unqualified. An old independently invoked foreground binary
that predates these guards cannot be made cooperative by a new CLI.
