# Project work from the terminal

After an interactive `okto-nexus connect`, the project prompt accepts your work
request. Nothing productive is submitted until you enter a request. Reopen it
with `okto-nexus work` from the same project, or select `--profile NAME`.
`connect --no-chat` and `connect --json` finish at setup without entering the prompt.

The prompt supports ordinary conversation and these explicit controls:

- `/status`, `/watch`: inspect or follow the current request.
- `/resume`: recover the same interrupted submission and its canonical receipt.
- `/sessions`: list authorized session references for this connection.
- `/answer ID`: review and answer one canonical native request.
- `/authorize`: review a new bounded execution grant when the previous authorization is unavailable.
- `/interrupt`, `/close`: request canonical interruption or session closure.
- `/new TEXT`: explicitly begin a new session with that work request.
- `/quit`, EOF or Ctrl+C: leave the observer. The service retains ownership of
  admitted work and its session; leaving never sends interrupt or close.

For scripts or individual commands:

```sh
okto-nexus work send --message "Inspect this project's failing tests" --json
okto-nexus work status --json
okto-nexus work watch --timeout 300 --json
okto-nexus work resume --json
okto-nexus work send --message "Continue with the reviewed fix" --json
okto-nexus work sessions --json
okto-nexus work chat --session-id SESSION_ID
okto-nexus work send --session-id SESSION_ID --message "Continue this session" --json
okto-nexus work send --new-session --message "Begin a separate task" --json
okto-nexus work interrupt --json
okto-nexus work watch --control --json
okto-nexus work close --json
```

An eligible session in Home exposes **Open this session in a terminal** with
the exact `work chat` command. Run it from the project directory with the
matching saved connection profile. Opening the prompt lets you inspect and
continue that session. Entering a new message is a separate action.

## Follow a live Codex session

Use a saved human operator login for the Nexus server and select the exact
workspace, Harness ID and session. The viewer requires the reviewed
Codex 0.170.0 Windows x64 frontend and a compatible local or Connector-hosted
app-server.

```sh
okto-nexus session attach --id HARNESS_ID --workspace-id WORKSPACE_ID --session-id SESSION_ID --operator-profile OPERATOR
okto-nexus session attach --write --id HARNESS_ID --workspace-id WORKSPACE_ID --session-id SESSION_ID --operator-profile OPERATOR
```

If Nexus asks for `--viewer-executable`, pass the absolute path to the reviewed
frontend and retry the same session. A refused viewer leaves the running turn
available in Home and for later attachment.

The default is read-only. `--write` also requires current executor capacity and
an execution grant for the selected session. Enter while idle records plain
text in the Nexus queue. During a turn, Enter reviews reorientation and Esc
reviews interruption. Confirming interruption pauses the queue. Nexus can also
queue a message for the next turn while the harness is busy.

Press Ctrl+] to detach. On Windows, closing the viewer's console also leaves
the session, running turn and queue with the same executor while its authorization
is valid. Run the same attach command to follow that session again. If a send
was in progress when the viewer closed, check the receipt reference printed in
the terminal with the original operator login before sending again.

If a Connector-hosted Codex viewer stops exchanging messages with Nexus, its
presentation expires and frees the terminal writer slot. Any request already
recorded in the queue remains with the session.

```sh
okto-nexus session receipt --id HARNESS_ID --workspace-id WORKSPACE_ID --session-id SESSION_ID --operator-profile OPERATOR --owner-generation GENERATION --intent INTENT
```

Use the operator's Nexus server address over HTTPS from another machine.

On a Connector host with the Nexus CLI and a saved human operator login,
`okto-nexus-connector connect -i --operator-profile OPERATOR` offers the native
viewer for a confirmed Codex or Pi connection. Without `-i`, the Connector asks
in a terminal and defaults to No. Use `connect --no-interactive` to skip the
offer. The result includes an exact command for the confirmed binding so you
can attach later without repeating setup.

## Native Pi viewer on Windows

For a live hosted Pi session on the reviewed Windows build, open the transcript
or open the native editor with the same operator login.

```sh
okto-nexus session attach --id HARNESS_ID --session-id SESSION_ID --operator-profile OPERATOR
okto-nexus session attach --write --id HARNESS_ID --session-id SESSION_ID --operator-profile OPERATOR
```

Enter records the text in the Nexus session queue and shows its receipt. If Pi
is working, the message waits for the next turn. Ctrl+C closes the viewer and
leaves the admitted work running. Taking over from another terminal writer
requires explicit confirmation.

If an Enter request has an unconfirmed receipt, use the original intent and
session generation printed by the viewer.

```sh
okto-nexus session receipt --id HARNESS_ID --session-id SESSION_ID --operator-profile OPERATOR --owner-generation GENERATION --intent INTENT
```

For Pi hosted by Connector, the same commands use the selected Nexus server.
Pass the exact `--workspace-id` with the Harness ID and use HTTPS from a
different machine. Enter queues text on the selected session. Ctrl+R reviews
reorientation at the next boundary and Ctrl+X reviews interruption of the
current run. The review requires a confirmed active run and a Connector that
supports exact-run controls. Confirming interruption pauses the session queue.

For a remote Pi session, use a Nexus CLI build that supports idle presentation
renewal. The reader and editor renew their presentation while waiting for output
or input. When the client stops exchanging messages with Nexus, its presentation
expires and the executor keeps the work and queue. Attach again to the same
session to resume watching. Older readers that send no application messages
expire after two minutes on a Server with this behavior.

If the Connector briefly loses its control link, it can resume the same link
with the existing execution lease. Wait until the link is ready, then attach
to the original session. Use the original receipt for any pending input.

When Nexus closes the session, queued messages that never received an operation
are marked as blocked and remain visible on their original receipts. Review any
message whose delivery is uncertain using its original receipt. To send an unsent
message to a different session, select that session and submit it explicitly.

## Follow or reorient a managed Claude session

On Windows, a local Claude session resumed into the Core-managed terminal
can be followed in a read-only viewer. Press Ctrl+C to leave the viewer while
the managed terminal and its work continue. Use Home or the explicit session
commands to control work.

```sh
okto-nexus session attach --id HARNESS_ID --session-id SESSION_ID --operator-profile OPERATOR
```

From an interactive terminal, review a reorientation for the selected session.
Claude needs a confirmed active turn. The command asks you to confirm interrupting
that turn before it submits the replacement. The same flow works on a Connector
that negotiated reviewed Claude controls.

```sh
okto-nexus session steer --id HARNESS_ID --workspace-id WORKSPACE_ID --session-id SESSION_ID --operator-profile OPERATOR
```

The receipt reports interruption and replacement separately. If delivery
is unconfirmed, use `okto-nexus session receipt` with the session, owner generation
and intent recorded by the first command.

## Request identity and authorization

`--request-id` supplies a stable client intent ID for an explicit submission.
Reusing the retained ID with changed text or selection is refused. Submission
records its ID before HTTP, resolves through the existing intent API and admits
that exact operation. After response loss, `resume` queries the same intent and
operation first; it never invents a replacement ID. If resolution is absent,
re-enter the exact original command. A new request after a confirmed refusal or
completed submission is a separate explicit action.

The Server may reuse an eligible existing session. If the remembered session
cannot continue, the CLI reports that fact; it does not fabricate restored
context or silently start over. Use `--new-session` to authorize a fresh session.
Reused openings correlate the initial turn by the submitting client intent, so
results of earlier requests are not presented as the new request's answer.

When execution authorization expires, is exhausted or has been revoked, use
`/authorize` in the prompt or `okto-nexus work authorize`. The review shows the
project identity, current grant states, permitted actions, expiry and budget.
An available grant covering the displayed project actions is reused; this command
does not add another one. A more limited grant remains unchanged when the operator
explicitly approves the displayed project actions.
Interactive issuance requires an explicit `y`. For scripts:

```sh
okto-nexus work authorize --minutes 60 --actions 20 --json
okto-nexus work authorize --review REVIEW_HASH --json
```

The lifetime starts at review and the displayed expiry does not move at commit.
Limits are 1..1440 minutes and 1..1000 runtime actions; the defaults are 60 and 20.
The new grant uses the canonical issuer and current project policy. It can admit
eligible authorized Nexus messages as well as explicit project requests; it does
not approve native questions or override a disabled identity, binding or policy.
If configuration or authorization changes, obtain a new review before issuance.

After an uncertain issuance, repeat `work authorize` to recover the same request
and receipt. Recovery does not extend its expiry, replenish its budget or undo
later revocation, including after a project configuration change. The receipt
describes the original issuance, not a claim of current execution readiness.
If login, vault access or receipt recovery fails while that issuance is still
pending, the CLI keeps the result `unconfirmed` with `possible_effect=true`.
Restore operator access and repeat the same profile's `work authorize`; do not
replace its checkpoint or create another authorization request to retry.
Reviews show at most 50 grant records and state when more exist; all records
participate in the current-state check.

Renewal leaves existing grants, sessions and leases unchanged. A session bound
to an expired or exhausted grant does not acquire the new grant. Inspect it and
explicitly close it when appropriate, then use `work send --new-session` or
`/new TEXT` for new work. No request is resumed or submitted by authorization,
reconnect, observation or service restart.

`status` and `watch` distinguish admission, native stage, session readiness,
pending questions and canonical results. `watch` in JSON mode prints changed
observations as JSON lines. Observation timeout leaves the request running.
`work events --json` reads the existing canonical event stream; use
`--after-sequence` and `--stream-epoch` for later pages. Gaps and truncation are
reported rather than filled from logs. `steer --message TEXT --target-turn-id ID`
uses the canonical native-turn target. An interrupt without a turn ID targets
the current run at execution time.

Native questions are displayed with agent, session, request ID and expiry.
Supported forms include Codex questions, Claude AskUserQuestion, bounded MCP
elicitation fields and Pi input/select/confirm/editor. Options and booleans have
no preselected response. Permissions require explicit `yes` or `no`; input
requests can be answered or denied. The same Server checks actor, recipient,
revision, scope, expiry and the exact native schema. Text sent to a model is
never interpreted as a permission decision.

For a noninteractive decision, read the exact review first:

```sh
okto-nexus work answer --approval-id REQUEST_ID --json
okto-nexus work answer --approval-id REQUEST_ID --decision approve --review REVIEW_HASH --answer-file answer.json --json
okto-nexus work answer --approval-id REQUEST_ID --decision deny --review REVIEW_HASH --json
```

`answer.json` is a UTF-8 native response object, limited to 16 KiB. Omit it for
a permission approval or denial. The returned `review_revision` is the value for
`REVIEW_HASH`. The file is read only for that explicit submission. Only decision
IDs, CAS metadata and a response digest enter the local checkpoint. An uncertain
answer cannot be replaced by a different answer; inspect its durable result or
re-enter the same response. A confirmed validation refusal allows correction.
Recorded decisions and native delivery are shown separately, including refusal
before an effect and uncertain delivery.

The local files under `terminal/work` contain bounded references/checkpoints,
not prompts, answers, results or a parallel conversation history. The Server
retains the canonical records. The selected project profile is locked while a
CLI session uses it; another writer receives `PROFILE_BUSY`. Commands inspect
the service and do not bootstrap an absent installation. Use `connect` to start
or reuse it. Explicit project/profile conflicts and changed canonical bindings
are refused.

Exit codes: 0 for successful observation, admission, review or normal observer
exit; 2 for argument errors; 3 for refused/unconfirmed work, a question awaiting
a separate answer, native delivery refusal or an observation deadline; 130 for
Ctrl+C. Admission exit 0 does not prove task completion: inspect the returned
state and receipts.

The same facade accepts a saved [human operator profile](terminal-operator.md)
for an already approved binding on a remote Server. To create a remote project
connection, use the implemented [Connector onboarding flow](remote-project-setup.md).
Its real-provider productive campaign remains separately pending. Native decisions require the
existing service setting `feature_hitl=true`. Initial project setup includes
reviewed activation when the Server has no explicit policy; it preserves an
existing disabled policy and any later changes. Work itself does not enable it
and reports native delivery refusal when disabled. Native user-login campaigns
and productive real-provider/context qualification remain separately pending.
