# Local project connection from the terminal

For an existing agent's external MCP client, use
[`connect --mode participant` or `init --mode participant`](terminal-participant.md).

`okto-nexus connect` starts or reuses the selected local Server and uses its
existing operator setup API. The review proposes a persistent project identity,
or reuses an explicitly selected existing agent. In an interactive terminal,
successful setup enters the [project work prompt](terminal-work.md). `--no-chat`
returns after setup. `configured` itself does not mean a live session or completed task.

```sh
okto-nexus connect --client codex --project .
```

The review shows the new identity's suggested name, role and coordination
permissions, local project, workspace, provider login directory, installation
check and execution limits. The project preset keeps the harness's
model and project instructions, requires native tool decisions, and requests
60 minutes / 20 actions of canonical execution authorization. The new identity
can use direct/channel messages, handoffs, artifacts and events through the
ordinary authorization checks. Broadcasts, channel creation, capability changes,
experimental memory and workspace path enumeration are disabled. Communication
is limited to 60 messages/minute and 10 recipients. The preset grants no global
administration or self-approval authority. Automatic handoff claiming is disabled
for the new identity, including when globally enabled. The connection test requests a model response and can incur
provider usage; the terminal asks for consent before that test. Finish uses the
existing configuration transaction to create the identity, workspace, binding
and grant together. Review and the connection test do not create an agent. No
project task is submitted by setup.

When the Server has no explicit native-decision policy, this same review offers
to enable Server-wide human review (`feature_hitl`) at Finish. This enables
native questions/permissions and matching coordination approval rules; every
decision still requires its authorized recipient. Review/Test do not change the
setting. Its stored value commits with the setup receipt, then becomes effective
in the running service. A late failure rolls back the setting with the setup.
An already enabled policy is reused. An explicit disabled policy, whether stored
or supplied by CLI/environment (including `false` equal to the default), is
preserved and diagnosed. An operator must resolve that policy before using this
route; setup does not override it. A concurrent policy change requires review.

Use `--agent reviewer` to reuse an existing authorized identity. Its name, role,
permissions and automatic handoff policy are preserved. For a new identity,
`--new-agent unused-id` and `--name "Project helper"` optionally replace the
suggested ID and name. The generated ID is saved with the review and stays the
same on resume. If another operation claims that ID before Finish, setup refuses
to adopt it. A new identity's root credential is initialized by the ordinary
agent creation service; no permanent key is exported to the terminal profile or
Finish response. Managed execution uses the existing scoped capability system.

For an already running Server, inspect and approve the exact saved review:

```sh
okto-nexus connect --profile project-review --agent reviewer --client codex --project . --plan --json
okto-nexus connect --profile project-review --approve REVIEW_REVISION --json
```

Replace `REVIEW_REVISION` with the displayed hash. `--plan` does not start the
service or run installation/model probes; it can save a non-secret review under
the selected Nexus home. Use the ordinary `connect` command to start the service
when required. Service selection options such as `--home`, `--host` and `--port`
use the same saved context and ownership checks as `service start`.

Reopen with `connect` from the same project, or `connect --profile project-review`.
An existing profile reads the current canonical binding without applying defaults
again. After response loss it recovers the same setup receipt, observes an already
submitted test, and never submits another test when its result is unavailable.
If the version-check response is lost, the same invocation reads the canonical
inventory for the reviewed Server, executor and installation within the observation
budget. It does not repeat the version command. The model test starts only after
that selection is confirmed ready; an expired budget or changed identity preserves
the saved checkpoint without starting a new model test. Changed explicit choices conflict with
the profile rather than silently rewriting it.
Expired or exhausted execution authorization is reviewed separately with
`work authorize` (or `/authorize` in the project prompt). Reconnect and service
restart never renew it automatically. See [terminal work](terminal-work.md)
for limits, receipt recovery and the effect on existing sessions.

For an explicitly selected existing agent, a unique authorized binding for the
local project is reused. Ambiguous connections require its canonical
`--binding-id` and matching agent/project. Identity is not guessed from a
folder or connection name. Multiple observed harnesses/installations require
`--client` / `--candidate-ref`. `--provider-home` names the provider login directory
on this Server host; this command does not log in for you. Paths are local to the
selected Server. Continue using the Connector CLI for host setup. An operator
can associate an already approved binding on a remote Server using
`--operator-profile`, `--agent` and `--binding-id`; see
[remote operator access](terminal-operator.md). The local project folder then
identifies the operator's shortcut and does not replace the host mapping.

Profiles contain setup IDs, reviewed configuration, baseline revisions and
binding references, not credentials or conversation history. Ctrl+C ends the
terminal observer, leaving the Server and submitted test under their existing
ownership. A test timeout does not cancel execution. `--json` emits the current
state; exit 0 means a valid plan, configured connection or declined interactive
review, 2 is argument grammar error, 3 is a refusal/incomplete observation and
130 is Ctrl+C. Inspect the JSON state and `possible_effect`, not only the exit code.

## Optional startup at user login

On the local Server host, include `--start-at-login` in the initial command:

```sh
okto-nexus connect --start-at-login
```

The same project review names the effective user, Server home, resolved Python
environment and startup effects. After canonical Finish, the existing lifecycle
drains and stops the Server, installs its user logon task, and starts it through
that task. Active work can delay this transition; it does not force termination.
The connection test and native installation are separate effects covered by the
displayed review, not a distributed transaction. Provider credentials stay in the
existing user context and are not copied into the task definition.

Omit this option to retain the current service mode. To remove it from an
unapproved saved review, use `--no-start-at-login --plan`, then approve the new
revision. This does not disable an existing integration. After setup has been
approved, use the explicit `service disable --user` / `service uninstall --user`
commands for the selected instance. Reconnect does not reinstall or reenable an
integration changed later by the user.

For an already configured project, `connect --start-at-login` presents a startup
review alone; its approval does not repeat Finish, a model test or grant issuance.
`--plan --json` and `--approve REVIEW_REVISION --json` also work for this review.
An already enabled task is reused; a disabled task requires the reviewed enable
effect. Host context or native definition changes refuse the old review.

If native installation or readiness is incomplete, JSON reports
`state: login_start_pending` and `setup_state: configured`. Resume the same
`connect --profile NAME`; its separate startup checkpoint is recovered before
ordinary startup, and the committed project receipt remains intact. Unconfirmed
native registration is diagnosed by the existing installer without creating a
second task or falling back to a detached Server. `--plan` remains observational.

The current installer supports Windows user logon tasks. This option does not
promise startup before login, survival after logout or restored work after reboot.
POSIX native installation remains unqualified; on-demand use is still available.
An operator profile targeting a remote Server cannot install a task on this client
as a substitute. On the Connector host, its `connect`/`configure` wizard offers
the corresponding local choice in Connector `0.0.12`; its service CLI remains
available for explicit later changes. Native login qualification remains pending.

The versioned preset origin is retained in the canonical Finish receipt and
exposed by setup reads. Dashboard and terminal still use the same binding,
runtime policy and harness configuration. Existing-client initialization uses
the [participant flow](terminal-participant.md); new remote project identities use
[remote project setup](remote-project-setup.md). Their implemented setup contracts
do not establish real-provider qualification. Reconnect and repeated Finish do not re-enable a policy
disabled after setup. A recorded decision whose native delivery is refused is
shown explicitly. New service contexts retain which configuration values were
explicit; frozen launch arguments do not pin defaults. Older contexts without
that provenance keep their previous stored-override behavior, but cannot
automatically initialize a policy whose original source is unknown.

For an existing remote agent, the default Connector wizard requests this same
preset origin. The operator's binding proposal includes the configuration, grant
and native-decision policy effect in one review. Finish commits them together;
policy changes before the decision or application require a new proposal.
An explicitly disabled Server policy is preserved. Imported configurations and
older saved requests do not implicitly initialize native decisions.
The Connector keeps its participant credential; the operator decides from their
authenticated Nexus terminal. Replaying the original binding apply after a lost
response recovers the receipt and current policy without restoring revoked grants.

For independent diagnostics, use `okto-nexus doctor --profile NAME`. Add
`--check-server` to inspect current operator authority, binding and saved work
through bounded GET requests. [Doctor](terminal-doctor.md) never starts the
service, applies setup or submits work; UNKNOWN is distinct from failure.

Reconnect preserves the saved configuration even when the recommended preset
changes. To review optional adoption or a newer revision, use
[`okto-nexus preset --plan --profile NAME`](terminal-preset.md). Its explicit diff
includes configuration changes, preserved choices, grant/boot invalidation and
any new authorization or model-test effects before approval.
