# Project work from the terminal

After setup in a terminal, `okto-nexus connect` asks whether to open the native
viewer and defaults to No. Use `connect -i` to request it or `connect
--no-interactive` to skip the offer. `connect --no-chat` or `connect --json`
finishes at setup. Use `okto-nexus work` from the project or with `--profile
NAME` to open the Nexus project prompt and submit an explicit work request.

For local `connect -i`, sign in with `okto-nexus operator login` on the same
loopback origin as the local service. Nexus uses a single saved human login
for that origin and Server. If you have several matching logins, choose one
explicitly with `session attach --operator-profile OPERATOR` and the connection
and session selectors below.

If the connection has no live session, Connect asks separately before opening
an empty session. Enter declines. An approved opening uses the current grant
and runtime policy, then displays the exact session once it is ready. Review
missing or expired authority through `work authorize`. If an opening receipt
is uncertain, requesting the viewer again checks that same receipt. No project
message is submitted by this flow.

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

## Choose a session action

Use the Nexus work prompt for Operator work requests. A supported native
viewer can submit a message as the harness user through the session queue.
The queue records a receipt before delivery. A queued message waits for a new
turn. A reviewed steer targets the current turn at a boundary the harness
supports. Queue acceptance and native delivery have separate receipt states.

| Intent | Action |
| --- | --- |
| Follow an existing live session | Use `session attach` with its exact session ID. Detach to leave work and the queue with the current executor. |
| Continue work in a live session | Select it in Home or use `work chat --session-id SESSION_ID` and submit the next request. |
| Resume retained native history | Use `session resume` in a terminal for an eligible retired source on the embedded executor or a Connector that supports saved resume for the selected adapter. Confirm the successor opening. Nexus checks verified history and exclusive ownership. The original queue stays with the source. |
| Recover an interrupted submission | Use `work resume` for a Nexus work request, or `session receipt` with the original intent and owner generation for native input. If a saved resume lost its response, run the same `session resume` command to recover its receipt. |
| Start a separate session | Use `session open` to confirm an empty session, or `work send --new-session` with a first request. Check an unconfirmed receipt before deciding whether to send again. |
| Interrupt or close work | Use the explicit interrupt or close control. An interruption targets the current run. Closing retires the session and leaves its unsent queue receipts on the original session. |

```sh
okto-nexus session list --id HARNESS_ID --workspace-id WORKSPACE_ID --operator-profile OPERATOR
okto-nexus session open --id HARNESS_ID --workspace-id WORKSPACE_ID --operator-profile OPERATOR
okto-nexus session resume --id HARNESS_ID --workspace-id WORKSPACE_ID --session-id SOURCE_SESSION_ID --operator-profile OPERATOR
```

If `session list` reports more sessions, repeat it with the same connection
and pass the reported cursor as `--after-session-id`. In JSON output, use
`next_after_session_id` while `has_more` is true.

`session open` uses the connection's current authorization and leaves work and
pending messages with their original session. It prints the new session ID
after the Server confirms the opening. If the opening is unconfirmed, repeat the
same command to recover its receipt before requesting another session.
A recovered opening may refer to a session that has already ended. In that
case the terminal reports the original session and receipt and settles the
local checkpoint. A result whose effect remains uncertain stays pending.

The saved-resume command requires a human operator session that the Server
recognizes as local. Review the source session, workspace and host before
confirming a successor. Press Enter to cancel. After an admission, repeat the
same command with `--json` to read its receipt without opening another session.
A confirmed opening whose successor has since closed returns `resume_closed`
and exit code 1, with the original successor ID and receipt. If the outcome is
still uncertain, `resume_unconfirmed` keeps the receipt available for recovery.
An unavailable saved context does not open a fresh conversation.

For a live session, use `session attach` when the harness supports it. Work
in the background stays with the current executor, even after a turn ends.
If the session owner or executor connection changes between listing and
confirmation of the session details, list the sessions again and review your
choice.

The reviewed Pi 0.87.1 installations with Node 24.15.0 on Windows x64 and
Linux x64 support saved resume on the local Nexus host. Use the approved
workspace and Pi profile of the original session. After a verified close,
the successor loads the same Pi branch. Repeat the command to recover its
receipt if the result is unclear.

For a session on a Connector, select the original Harness ID and workspace.
The reviewed Windows x64 builds of Codex 0.157.0, Pi 0.87.1 and Claude Code
2.1.328 can reopen saved history on that same Connector after an acknowledged
close. The reviewed Linux x64 installation of Pi 0.87.1 with Node 24.15.0 can
also reopen saved history on its original Connector.
Keep the approved workspace and launch configuration in place. Claude also
requires the same reviewed `plan` profile and native history. The Connector
checks the saved history on its own host and refuses a changed or unavailable
source.
Follow the detach key shown by the attached viewer. Ctrl+C in a harness
started outside Nexus follows that harness's terminal behavior.

Session interaction is off by default. A Server administrator can enable the
session interaction flag with
`OKTO_NEXUS_RUNTIME_SESSION_INTERACTION_ENABLED=true`. The available actions
still depend on the exact harness build, platform, executor, session state and
operator authority. Use Home or `session list` for the current session and
review each action there or in its terminal command. For scripts,
`connect --json` reports setup and the receipt. Interactive viewers need a
terminal.

The tested builds, control timing and remaining qualification are recorded
by session mode and executor. [Session capability matrix](../NEXUS_SESSOES_INTERATIVAS_R1/execution/si027-session-capability-matrix.md)

## Roll back the session interface

Choose **Use classic Home** in **Settings** to switch the current browser
back to its classic view. The Server continues to reconcile admitted work
and process its queue. Return to operational Home or use the terminal to
check the same session.

For a Server rollback, turn on **Pause new session messages** under
**Settings → Runtime → Global runtime defaults** and save. This pauses new
messages from the session composer and native viewers while the current
executor continues processing and reconciling accepted messages. Use
**Pause queue** on the exact session if its pending messages need to wait.
Clear the global setting and save to accept new session messages again.

The session interaction flag applies at Server startup. With the flag off,
the Server refuses new queue submissions and can still reconcile retained
work. After a restart retires an
embedded session, unsent inputs keep their original receipts on that
session. Use the original intent and generation to check uncertain delivery
before deciding whether to submit new work.

The global pause works with the current package and database. Rolling back to
a package that predates migration 190 requires a consistent backup from
before the migration. Reconcile accepted work and stop the runtime before
restoring a database copy. Keep the current database and use the interface
rollback if the database contains work recorded after that backup.

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
text in the Nexus queue. During a turn, Enter reviews reorientation. Esc or
Ctrl+C opens an interruption review for the active turn. Ctrl+Y confirms the
interruption and pauses the queue. Ctrl+N cancels the review. Nexus can also
queue a message for the next turn while the harness is busy.

Press Ctrl+] to detach. On Windows, closing the viewer's console also leaves
the session, running turn and queue with the same executor while its authorization
is valid. When the viewer returns to the shell, use the **Reattach to this session**
command to follow the same session again. If a send
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

<a id="native-pi-viewer-on-windows"></a>

## Native Pi viewer

For a live hosted Pi session, open the transcript or the native editor with the
same operator login. The commands work on Windows and Linux terminals. The
runtime host needs a reviewed installation of Pi 0.87.1 and Node 24.15.0 on
Windows x64 or Linux x64.

```sh
okto-nexus session attach --id HARNESS_ID --session-id SESSION_ID --operator-profile OPERATOR
okto-nexus session attach --write --id HARNESS_ID --session-id SESSION_ID --operator-profile OPERATOR
```

Enter records the text in the Nexus session queue and shows its receipt. If Pi
is working, the message waits for the next turn. Ctrl+] closes the editor and
leaves the admitted work running. Taking over from another terminal writer
requires explicit confirmation.

In an interactive `session attach --write`, Ctrl+O starts the Nexus review
for a separate empty session. Finish any draft or pending control first.
Ctrl+Y confirms the opening and returns to the shell with a command to attach
to the exact new session. Ctrl+N cancels and stays in the original viewer.
The original session keeps its queue and has its own reattach command.
If the opening is unconfirmed, use `session open` on the same connection to
recover the recorded request and get its exact session ID.

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
The reviewed Linux runtime supports reorientation and interruption through the
same exact-run review. After a verified close, a Connector can reopen the saved
history from that same Linux runtime.

If a slow terminal can no longer receive updates, Nexus releases its
presentation while the session keeps running. Reattach to the same session
for a fresh viewport. Check the conversation for output you missed and the
original receipt for any unconfirmed input.

The hosted Pi runtime keeps draining stdout and stderr with no viewer
attached. It keeps up to 200 diagnostic chunks of 4,096 characters each
from stderr. Nexus keeps up to 1 MiB of UTF-8 text per canonical result
and sets `output_truncated` for longer output. Reattach to the live Pi
session for a recent viewport of its native transcript.

For a remote Pi session, use a Nexus CLI build that supports idle presentation
renewal. The reader and editor renew their presentation while waiting for output
or input. When the client stops exchanging messages with Nexus, its presentation
expires and the executor keeps the work and queue. Attach again to the same
session to resume watching. Older readers that send no application messages
expire after two minutes on a Server with this behavior.

If the Connector briefly loses its control link, it can resume the same link
with the existing execution lease. Wait until the link is ready, then attach
to the original session. Use the original receipt for any pending input.

If the outage outlasts that window, the Connector must reconcile the old
execution before the new link becomes ready. Check the original session and
its receipts before deciding what to send next.

When Nexus closes the session, queued messages that never received an operation
are marked as blocked and remain visible on their original receipts. Review any
message whose delivery is uncertain using its original receipt. To send an unsent
message to a different session, select that session and submit it explicitly.

## Follow or reorient a managed Claude session

On Windows x64, an explicit empty opening from `session open` or Connect can
start the reviewed Claude Code 2.1.328 build in the Core-managed terminal.
This requires session interaction, the approved `plan` settings, a reviewed
Claude state directory and a current execution grant. The opening sends no
prompt. The native viewer is available when the selected session has a
managed terminal.

Attach with the exact session ID to follow a new or resumed managed session
in a read-only viewer. Press Ctrl+C to leave while the terminal and its
work continue. Use Home or the explicit session commands to control work.
If older output has rolled out of the buffer, a new viewer shows a notice
and displays the retained output.

```sh
okto-nexus session attach --id HARNESS_ID --session-id SESSION_ID --operator-profile OPERATOR
```

The same command follows a managed Claude terminal on a Connector that
negotiated Claude presentation with the Server. Sign in as a Nexus operator
and select the exact session. The reviewed remote setup uses Claude 2.1.328
on Windows, an approved provider directory and credential reference, and
the `plan` permission mode. The Connector uses its existing outbound
connection. Ctrl+C detaches the read-only viewer and leaves work with the
Connector.

After canonical closure, a local managed session with verified saved history can
be selected by `session resume`. Confirm the successor before sending more
work. The saved conversation retains its native identity across that opening.

From an interactive terminal, review a reorientation for the selected session.
Claude needs a confirmed active turn. The command asks you to confirm interrupting
that turn before it submits the replacement. On a Connector, reorientation
requires the separate reviewed Claude control capability.

```sh
okto-nexus session steer --id HARNESS_ID --workspace-id WORKSPACE_ID --session-id SESSION_ID --operator-profile OPERATOR
```

The receipt reports interruption and replacement separately. If delivery
is unconfirmed, use `okto-nexus session receipt` with the session, owner generation
and intent recorded by the first command.

To interrupt the selected Claude turn and pause its queue, confirm the
review from an interactive terminal. For a Connector session, this requires
the negotiated Claude interruption capability. The queue retains pending
messages until the operator explicitly resumes it.

```sh
okto-nexus session interrupt --id HARNESS_ID --workspace-id WORKSPACE_ID --session-id SESSION_ID --operator-profile OPERATOR
```

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
