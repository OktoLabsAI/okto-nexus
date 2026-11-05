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
okto-nexus work send --session-id SESSION_ID --message "Continue this session" --json
okto-nexus work send --new-session --message "Begin a separate task" --json
okto-nexus work interrupt --json
okto-nexus work watch --control --json
okto-nexus work close --json
```

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
for an already approved binding on a remote Server. Unified Connector onboarding
and its full productive campaign remain unfinished. Native decisions require the
existing service setting `feature_hitl=true`. Initial project setup includes
reviewed activation when the Server has no explicit policy; it preserves an
existing disabled policy and any later changes. Work itself does not enable it
and reports native delivery refusal when disabled. Start-at-login review and
productive real provider/context qualification remain required before M1 is complete.
