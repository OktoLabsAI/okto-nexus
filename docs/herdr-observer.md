# Herdr observer: local Windows, real Herdr and synthetic-process qualification

This adapter observes an existing local Herdr session and publishes external
activity to Nexus. Qualification uses the real Herdr 0.9.5 distribution and a
synthetic native process. It does not establish compatibility with a real AI
client, model or provider. The installed-package campaign passed, including two
Herdr sessions, actual process replacement and source restart. See the
[qualification evidence](../plans/agent_ops/evidence/pr09-herdr.md) for exact scope.

The observer is a separate, explicitly launched CLI process. It does not start
Herdr or Nexus, install a Connector, register an executor, or provide an MCP
facade. It neither sends input nor starts, focuses or stops the observed agent.
An observation receipt acknowledges telemetry, not task or handoff success.

## Supported contract and prerequisites

The adapter accepts local Windows Herdr **0.9.5**, live protocol **22**, and
schema version **1** with this exact raw schema SHA-256:

```text
9e2af207e9aa8183d4aeca5fde9cc48e7909bb40cdbd7cf21608a6d3ea78075b
```

Use an explicitly approved absolute executable path and an explicit session
name. The literal session `default` is allowed when selected deliberately; an
omitted session, focused-pane default or pane alias is not. Checking the offline
schema alone does not establish a live compatible server. Each observation also
checks live status and reads the selected session. Herdr documents its schema
and CLI wrappers in the [Socket API](https://herdr.dev/tui/docs/socket-api/);
the pinned distribution is [release 0.9.5](https://github.com/herdrdev/herdr/releases/tag/v0.9.5).

Before binding:

1. Start and select the intended local Herdr session through your existing
   workflow. Identify its exact pane ID and the intended native executable.
2. Follow [Register and approve](external-observations.md#register-and-approve)
   to enable OBS, approve the agent and workspace, register a source and an
   instance, and issue a publish token for that exact instance generation.
   `observations.publish` must currently be explicitly true. A publish token
   cannot register, rotate or renew its own scope.
3. Choose an existing private local directory for a new journal. Keep one
   journal and one publisher for each approved instance generation. The observer
   locks its journal; separate journals are not a coordination mechanism.

The Nexus origin must be HTTPS or loopback HTTP. Herdr's remote-machine/SSH
selection is unsupported. Other Herdr versions and platforms require separate
qualification, even when their documented API looks similar.

## Preview and approve the exact binding

These PowerShell examples use placeholder paths and IDs. Replace them with
existing approved values; `--generation` is the current Nexus generation, not a
locally allocated counter. The journal's parent directory must already exist.

```powershell
$observerBinding = @(
    'observe', 'herdr', 'bind',
    '--state', 'C:\Private\NexusObserver\reviewer.json',
    '--herdr-executable', 'C:\ApprovedTools\Herdr\herdr.exe',
    '--session', 'approved-local-session',
    '--namespace', 'approved-installation-namespace',
    '--pane', 'w1:p2',
    '--server', 'http://127.0.0.1:8080',
    '--source-id', 'approved-source-id',
    '--instance-id', 'approved-instance-id',
    '--generation', '1',
    '--interval', '15',
    '--ttl', '90'
)
okto-nexus @observerBinding
```

The preview reads the live source and prints the selection hash, binding,
destination, sampling interval and TTL. It saves no binding and publishes no
report. Review the executable image, process identity, pane/session and Nexus
destination. Then repeat the same selection with the exact returned hash:

```powershell
okto-nexus @observerBinding --approve-selection 'sha256:<exact-preview-hash>'
```

Approval performs a new live read. A changed binding or destination fails the
hash check; inspect a new preview instead of copying the old approval. An
existing journal is never overwritten. The namespace identifies the intended
Herdr installation in the binding; it is not evidence of process identity or a
grant of Nexus authority.

Identity combines the local host hash, Windows PID and process creation time,
the selected native executable image path, Herdr session and pane topology,
terminal ID, and any available ID-based agent session reference. A held Windows
process handle must remain alive across the source snapshot, with matching
process selection before and after it. A PID or model name alone is insufficient.
The executable image path shown in the preview is part of the approved binding;
it is not a code signature or executable-content attestation.

Shell-only selections, known interpreter/wrapper executables, ambiguous process
selections and inaccessible process identity are refused. A wrapper can survive
replacement of its child, so its birth time cannot prove that child's identity.
The process bracket checks the qualified metadata contract; it is not an atomic
transaction across Herdr and Windows. Herdr's Windows selection logic is in the
[pinned platform implementation](https://github.com/herdrdev/herdr/blob/v0.9.5/src/platform/windows.rs).

## Run and inspect local status

Provision `MY_OBSERVATION_PUBLISH_TOKEN` through your approved secret channel
before running these examples. Pass only its environment-variable name on the
command line. The journal contains no bearer, and the token is not passed to the
Herdr subprocess.

```powershell
okto-nexus observe herdr run --state 'C:\Private\NexusObserver\reviewer.json' --token-env MY_OBSERVATION_PUBLISH_TOKEN --once
okto-nexus observe herdr status --state 'C:\Private\NexusObserver\reviewer.json'
```

Without `--once`, the observer samples and publishes repeatedly until stopped or
an error occurs:

```powershell
okto-nexus observe herdr run --state 'C:\Private\NexusObserver\reviewer.json' --token-env MY_OBSERVATION_PUBLISH_TOKEN
```

The default interval is 15 seconds and TTL is 90 seconds. The interval accepts
5–300 seconds; TTL accepts 30–3,600 seconds and must be at least twice the
interval. Current Server limits still apply. The loop waits after a completed
publication; it does not promise an exact sampling cadence. Ctrl+C stops only
the observer. It does not stop Herdr, revoke authority or manufacture an idle
report. Existing observations age under the
[OBS freshness rules](external-observations.md#publish-a-fresh-snapshot).

`status` reads local binding/checkpoint metadata, including pending state and
the last receipt. It does not contact Herdr or Nexus and cannot establish current
remote freshness or authorization. It may acquire/create the local journal lock.

## Recover a pending report explicitly

Before a POST, the observer durably saves the complete report and reserves its
sequence. A pending report blocks new samples from being published. Preserve
the journal after a timeout, crash, invalid receipt or checkpoint-write failure.
The [publish-only helper](external-observations.md#use-the-publish-only-python-helper)
defines the receipt and error contract.

To recover only the exact historical receipt:

```powershell
okto-nexus observe herdr run --state 'C:\Private\NexusObserver\reviewer.json' --token-env MY_OBSERVATION_PUBLISH_TOKEN --retry-pending --once
```

This sends the saved report unchanged, including generation, sequence, observed
time and TTL. It neither samples Herdr nor requires the old Herdr process to be
running. A successful result is `historical_receipt`; it does not describe current
activity or extend the old report's validity. Without `--once`, a successful
recovery is followed by fresh source validation and normal observation.

Every replay still needs current authorization. An expired token must be
replaced through [canonical management](external-observations.md#read-renew-revoke-and-retire)
for the applicable source and generation. Replay does not restore a revoked
grant. There is no automatic retry or renewal, including after a response with
`retry_after_seconds`.

A pending report can be discarded only when the retained attempt history proves
no admission and contains **no uncertain attempt**:

```powershell
okto-nexus observe herdr run --state 'C:\Private\NexusObserver\reviewer.json' --token-env MY_OBSERVATION_PUBLISH_TOKEN --discard-refused --once
```

This preserves the reserved sequence and then attempts one fresh observation;
it is not a command that merely deletes local state. A later 401/403 or other
known refusal cannot erase uncertainty from an earlier attempt. Discard is
refused while uncertainty remains. The two recovery flags are mutually
exclusive and require a pending report. Never edit the journal, reset a sequence,
or rotate a generation merely to conceal an unresolved publication.

On `checkpoint_failed`, retain any emitted validated receipt together with
`remote_admitted` and `outcome_unknown`: remote admission and local durability
are separate facts. Only a validated receipt resolves an uncertain publication.

## Freshness, completion and reassociation

Transport loss stops the run. A later explicit run must obtain a fresh live
snapshot before publishing current activity; historical backlog is not replayed
as a new observation. A reconnect alone does not prove identity continuity.
An identity mismatch, incompatible location change or counter regression
invalidates the binding, and `status` reports `reassociation_required`.

For an invalidated binding, inspect the old pending state first. Reassociation
requires the authorized Nexus instance-generation rotation, a token for that
new generation, and a new journal with a newly approved live preview. Reusing a
path, pane ID or PID does not authorize reuse of the old generation. Retain the
old journal and receipts for reconciliation.

Renaming an agent or changing a pane title does not alter the binding. Moving a
pane/workspace location, replacing its process, or changing its bound session
identity requires reassociation. Herdr distinguishes a pane location from an
agent alias and documents that moves change qualified pane IDs in
[Agent automation](https://herdr.dev/tui/docs/agent-automation/).

An initial `done` state establishes a baseline; it creates no new completion.
A later advancing, consistent completion sequence may produce a stable external
completion reference. Herdr `done` maps to OBS `idle`, never to canonical Nexus
task success. Repeated samples retain the same completion reference rather than
creating another completion. No observation claims, completes or verifies a
handoff, answers an approval, or releases execution capacity.

## Read boundary and optional plugins

The subprocess allowlist contains only version, offline schema, live server
status, session snapshot and pane process-info commands. Each invocation selects
the explicit local session and has bounded runtime and combined output size.
Inherited Herdr socket, remote-machine and pane-selection context is excluded.
Timeout cleanup stops only the spawned CLI child, not the Herdr server or the
observed process.

The adapter never calls `agent.read`, `pane.read` or `agent.explain`. It does not
retain terminal bodies, titles, labels, command lines or working directories
from source responses. Process-info contributes PID metadata only; the approved
image path comes from Windows identity inspection. The local journal retains
the binding and recovery metadata, so keep it private even though it has no
publish token.

Activity evidence is always `inferred`. Metadata does not establish whether a
particular status came from a trusted hook, screen detection or another source;
the excluded explanation/terminal surfaces cannot be used to promote it to
reported authority. A recognized agent name is not provider authentication.

No Herdr plugin or `herdr-plugin.toml` is required. A separately chosen plugin
could launch local code, but its manifest grants no Nexus permission and does
not strengthen observation evidence. Herdr plugins run with the local user's
authority and are not sandboxed, as described in
[Plugins: trust and security](https://herdr.dev/tui/docs/plugins/#trust-and-security).
