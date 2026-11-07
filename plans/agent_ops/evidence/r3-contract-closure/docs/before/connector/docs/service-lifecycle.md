# Connector lifecycle readiness

`okto-nexus-connector daemon status --json` reports the local component,
instance identity, generation, active and installed versions, and local
readiness separately from remote link/work readiness. Select an instance with
the global `--state-dir` option. Status does not create an absent state directory.

Ownership requires both an OS-held guard and matching process birth evidence.
The authenticated IPC response must agree on PID, instance, generation and
protocol/package version. A live owner with unavailable IPC is degraded, not
absent. Start waits for that same owner within its observation deadline and
never treats a transport error as permission for a competing launch. A draining
or incompatible owner is not reported as ready.

The instance is identified by canonical state directory, effective OS principal
and component. It is independent of Server/executor/agent identity. `remote_link`
and `work_state` remain `not_checked` in this local readiness projection; use the
existing status/doctor and canonical runtime operations for those facts.

Lifecycle stop sends the observed generation through the existing authenticated
IPC shutdown path. A durable shutdown receipt correlates its outcome. If the
process disappears without that confirmation, the CLI returns an uncertain
outcome instead of claiming successful drain. No PID file authorizes a kill.
Status exits 0 for ready/stopped, 3 for unready states; an unconfirmed stop exits
4. Existing foreground and daemon command names remain valid.

`python -m okto_nexus_connector.daemon --state-dir /absolute/path` respects the
explicit selection and remains in foreground for an external supervisor. The
existing state, vault, execution records, remote registrations and native
reconciliation remain authoritative. Transport shutdown joins attachment cleanup
without issuing a second cancellation during HTTP connection closure.

## Drain and an explicit force decision

`daemon stop` fences new productive work and capacity reservations while keeping
authorized decisions, lease reconciliation, results and acknowledgements alive.
The first request fixes the deadline. Timeout reports pending work or unknown
ownership; it never authorizes automatic force or a replacement process.

After that deadline, inspect the same instance and explicitly select its current
generation if containment is required:

```powershell
okto-nexus-connector --state-dir C:\absolute\connector-state daemon stop --timeout 30 --json
okto-nexus-connector --state-dir C:\absolute\connector-state daemon status --json
okto-nexus-connector --state-dir C:\absolute\connector-state daemon stop --force --expected-generation REVIEWED_GENERATION --timeout 30 --json
```

The owner rechecks generation and persists the supervisor stop intent even for
a direct authenticated IPC request. A premature force or stale generation is
refused. Force enters the existing containment contract for owned resources;
uncertain ownership remains pending with the process, IPC and lock retained.
Only confirmed release permits a drained result or restart. Signals and external
termination use a separate safety-containment path. No option kills an arbitrary
PID or infers work completion from elapsed time.

## Detached start and foreground ownership

`daemon start --timeout 45`, `daemon stop --timeout 60` and
`daemon restart --timeout 45` select the same instance. A launch guard serializes
concurrent CLI callers before a child exists. Its durable receipt prevents a
wait timeout or lost response from spawning a second daemon. The child acquires
the lifetime OS lock before constructing state/vault/runtime services, then
uses the existing foreground application. Explicit restart requires confirmed
canonical drain before selecting a new generation.

The first launch saves resolved Python/environment/state/working-directory
references. Later starts reuse them. Provider secrets and shell startup hooks
are not copied. Existing proxy policy resolves its named environment references
at launch; values are not saved in the service context. Existing vault backend
selection and fallback consent remain authoritative. Changing a proxy reference
requires that variable to be available to the launching OS context.

`daemon run` remains the foreground entrypoint for an external supervisor. It
refuses a competing instance or a selected installed Windows task. An interrupted
launch with uncertain ownership remains pending for observation/reconciliation;
deleting receipts or killing a PID is not a supported recovery shortcut.

## Windows user task

With the selected global `--state-dir`, `service install --dry-run` previews the
definition. `service install` asks for confirmation before enabling a task for this user's
future logins; `daemon start` starts it immediately. `service status --json`
observes installation, and `service uninstall` removes only the selected
owned task after controlled drain. Uninstall retains application state, vault,
history, logs and saved execution context. Dry run/status do not create an
absent state directory. For an already authorized scripted installation, use
the existing global `--non-interactive` option.

Task names include canonical instance identity. The receipt records the effective
principal and native definition fingerprint. External edits, an unowned selected
task or a legacy global task require explicit review. They are not overwritten
or adopted automatically. An installed start routes through Task Scheduler;
uncertain native outcomes retain their receipts instead of falling back to a
detached process. Native mutations recheck the fingerprint, but the OS does not
offer an atomic fingerprint-conditional operation against concurrent external
editors.

Stop records suppression of same-login recovery before authenticated IPC drain.
The installed worker exits without reopening admission after that stop; a new
login is a separate trigger. Neither logout survival nor availability before
login is promised. Bounded automatic crash recovery follows the shared Core
definition; qualification of actual crash/login behavior is still pending.

## Qualification boundaries

Windows disposable-process tests cover concurrent start, launcher exit, reuse,
restart, generation-correlated drain and the wheel installed outside the checkout.
Fake-native tests cover ownership conflicts, changed definitions, lost responses,
stop suppression and data preservation. Native Task Scheduler checks use only
`TASK_VALIDATE_ONLY`, including calls from worker threads; they do not install a
task. These are distinct from actual terminal closure, login/logout or service
credential qualification.

Linux systemd/macOS launchd installers remain legacy global templates. They have
not received the R3 instance ownership/reconciliation contract and are not
qualified by these Windows results. General definition reconciliation, upgrades and
real remote/provider/login/logout campaigns remain in progress. Exact evidence
and remaining scope are in `plans/agent_ops/user-service.md` and the Nexus R3 ledger.

`service enable --json` and `service disable --json` change only the selected
Windows task's enablement. They do not start, stop or cancel a current daemon;
use `daemon start` and canonical `daemon stop` for those operations. The queued
scheduled entry checks enablement before bootstrap. Disabled tasks remain owned
and cannot silently fall back to a detached daemon. Disabling also works when
the saved Python environment is unavailable; enabling validates its context.

Each mutation retains an intent before changing the OS. Repeat the same command
after a lost response to confirm an enablement-only result without another write.
An opposite request or unrelated native edit cannot clear that pending operation.
External enablement edits without a matching intent require review. The Core
comparison retains every field except the specific task Settings/Enabled value;
it cannot authorize privilege, command, principal or trigger changes. These
controls use scoped fake-native tests and native validate-only checks; actual
task registration/mutation campaigns remain separately qualified.

## Recover an interrupted detached launch

`daemon status --json` reports `launch_recovery.receipt_revision` for a retained
pending launch. A timeout never revokes it automatically. If its launcher was
interrupted before bootstrap, explicitly run:

```powershell
okto-nexus-connector --state-dir C:\absolute\connector-state daemon recover-start --expected-revision REVIEWED_REVISION --json
```

Recovery holds both the launch guard and daemon lifetime lock, verifies the
selected instance and exact receipt revision, and marks only that pending launch
aborted before bootstrap. A delayed child rechecks the receipt before creating
state, vault or Core runtime and exits. The command neither kills/adopts a PID
nor starts a replacement; use `daemon start` explicitly afterward. Installed
tasks, changed receipts, active/uncertain owners and launches past bootstrap are
preserved and refused. Runtime claims, identities, grants and uncertain effects
continue through their canonical reconciliation paths.

Repeating the same expected revision confirms a recorded recovery without a
second write. After a persistence response is lost, status remains authoritative;
repeat that same revision instead of deleting receipts. Recovery requires no
provider credentials and does not rewrite the saved execution context.

## Reviewed environment upgrades

`upgrade-plan` reads the selected installed Python and Core payloads and emits a
complete plan with a SHA-256 `plan_revision`. It does not drain, migrate, start or
change the service. `--output` creates a new UTF-8 file and refuses to overwrite
an existing file. The source context must already exist. Editable checkouts and
unordered/prerelease versions are not eligible targets in this protocol.

```powershell
okto-nexus-connector --state-dir C:\absolute\connector-state service upgrade-plan --python C:\target\Scripts\python.exe --output C:\review\connector-upgrade.json --json
okto-nexus-connector --state-dir C:\absolute\connector-state daemon stop --json
okto-nexus-connector --state-dir C:\absolute\connector-state service upgrade-apply --plan-file C:\review\connector-upgrade.json --expected-revision REVIEWED_REVISION --json
okto-nexus-connector --state-dir C:\absolute\connector-state daemon start --json
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
