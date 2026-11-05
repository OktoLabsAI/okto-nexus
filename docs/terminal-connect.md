# Local project connection from the terminal

`okto-nexus connect` starts or reuses the selected local Server and uses its
existing operator setup API. This initial implementation configures an existing
authorized agent. Agent creation and terminal work/session controls are still
under development; `configured` does not mean a live session or completed task.

```sh
okto-nexus connect --agent reviewer --client codex --project .
```

The review shows the agent, local project, workspace, provider login directory,
installation check and execution limits. The project preset keeps the harness's
model and project instructions, requires native tool decisions, and requests
60 minutes / 20 actions of canonical execution authorization. It does not change
agent identity, role or permissions, and does not opt into automatic broadcast
handoff claiming. The connection test requests a model response and can incur
provider usage; the terminal asks for consent before that test. Finish uses the
existing configuration transaction. No project task is submitted by setup.

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
Interrupted version checks are also observed before any later step. Changed
explicit choices conflict with the profile rather than silently rewriting it.

For an explicitly selected existing agent, a unique authorized binding for the
local project is reused. Ambiguous connections require its canonical
`--binding-id` and matching agent/project. Identity is not guessed from a
folder or connection name. Multiple observed harnesses/installations require
`--client` / `--candidate-ref`. `--provider-home` names the provider login directory
on this Server host; this command does not log in for you. Paths are local to the
selected Server. Continue using the Connector CLI for a Connector-hosted runtime.

Profiles contain setup IDs, reviewed configuration, baseline revisions and
binding references, not credentials or conversation history. Ctrl+C ends the
terminal observer, leaving the Server and submitted test under their existing
ownership. A test timeout does not cancel execution. `--json` emits the current
state; exit 0 means a valid plan, configured connection or declined interactive
review, 2 is argument grammar error, 3 is a refusal/incomplete observation and
130 is Ctrl+C. Inspect the JSON state and `possible_effect`, not only the exit code.

The versioned preset origin is retained in the canonical Finish receipt and
exposed by setup reads. Dashboard and terminal still use the same binding,
runtime policy and harness configuration. Start-at-login selection, creating an
agent in the review, participant initialization and the complete terminal work
cycle are not yet part of this command.
