# Coordination from the terminal

Use an existing [participant profile](terminal-participant.md). The profile selects
the Server origin, installation, authenticated agent and logical workspace.
These commands call the Server's canonical MCP tools; they do not start a
Server, open a canonical agent session, create an identity or select a provider.
`work` continues to handle native runtime operations through its existing API.

```bash
okto-nexus message send --profile author --to reviewer --workspace WORKSPACE_ID \
  --subject "Review context" --body-file context.md --json
okto-nexus handoff create --profile author --to reviewer --workspace WORKSPACE_ID \
  --title "Review implementation" --body-file task.md --wait --timeout 300 --json
okto-nexus handoff wait HANDOFF_ID --profile author --timeout 300 --json
okto-nexus request inspect REQUEST_ID --profile author --json
```

Messages are conversation/information. Handoffs assign canonical work. Choose
`--to AGENT`, `--broadcast`, or `--target-json '{...}'` explicitly; the client
never converts a routing strategy to obtain execution. `--to` cannot select
the sender. A supplied `--workspace`/`--workspace-id` must match the profile.

Message content may come from `--body-file`, `--body-stdin`, or `--body`.
Handoff `--title` and body form a JSON payload with those fields. For a different
canonical payload, use `--payload-json` instead. Handoff creation also accepts
`--visibility` (`private`, `eligible`, or `public`; default `eligible`),
`--acceptance-criteria` (JSON), `--verify-by` (JSON), and repeated
`--depends-on`. Message creation accepts `--channel-id`, `--parent-message-id`,
repeated `--artifact`, and `--no-reply`. The Server enforces all domain rules.

## Existing credentials and sessions

The CLI loads the profile's existing protected credential. A review-only
profile can use the hidden prompt, `--key-stdin`, or `--key-env NAME`. Only the
explicitly named environment variable is read. Content and key cannot both
consume stdin. No operator credential or automatic identity fallback is used.

Use `--session-id` to preserve an existing canonical conversation/session, with
`--session-secret-env NAME` when its proof is required. Secrets are neither
arguments to a saved request nor part of its digest. A resumed request retains
its original session ID; provide its proof again as needed. MCP SDK transport
initialization does not open or heartbeat a canonical agent session.

## Durable requests

Before a productive call, the client saves an ID, exact public-intent digest,
scope, original deadlines and non-secret session context. Content, results,
session proofs and API keys stay out of the checkpoint. Files live under
`HOME/terminal/coordination/PROFILE/`, using hashed filenames because a legal
request ID can contain `:`. The `latest.json` index holds one latest ID per
operation; prior request checkpoints remain addressable by their IDs.

The first command generates an ID. Repeating a creation command without
`--request-id` or `--new-request` resumes the latest request for that operation.
Supply identical content/target/context. Use `--new-request` for explicitly new
work, even when its content is identical. To revisit an older local request, use
`--request-id ID`. An explicit ID without a checkpoint requires `--new-request`
to declare a new intention; do not reuse an old ID for replacement work.

On resume, the first call is `coordination_request_get`. A retained reference
returns the original object/approval without another creation call. A known
pending approval remains that approval; this participant never decides it.
If no receipt exists and no receipt was previously confirmed, an explicitly
resumed creation may send the same ID/content only within its original window.
A missing previously confirmed receipt is uncertain and never recreated.

The contract is 30 days. The CLI compares both its persisted local deadline and
the original Server-time deadline against current clocks. A backward clock,
expired window, tombstone or inconsistent reference cannot renew the request.
`nexus_info.coordination_requests.observed_at` is a current clock snapshot, not
a new retention deadline. Servers lacking the contract are diagnosed before
creation; the CLI does not silently remove `client_request_id` or promise safe
retry through an older surface. No receipt can prove external exactly-once
effects. After uncertainty, keep the same ID; do not automatically create a new
one merely to obtain a successful response.

`request inspect` reads a reference without resubmitting. It can infer the
operation from a unique local checkpoint. Use `--operation message_create` or
`--operation handoff_create` for an imported ID or an ambiguous selection.
Without an ID it selects the unique matching latest local request. Inspection
does not create a missing checkpoint directory. `NOT_FOUND` is an uncertain
result: absence after retention does not prove that no action committed.

## Passive completion observation

`handoff wait` observes the exact handoff using `event_cursor`, `handoff_get`
and `event_wait`, all with the logical workspace and `passive=true`. The cursor
precedes the first snapshot. Each long-poll window is followed by a canonical
reread, even when no completion event is visible to the creator. `COMPLETED`
satisfies the wait; `VERIFYING` does not. `REJECTED` and `CANCELLED` end the wait
without success. Message delivery/read receipts and native idle do not satisfy
a handoff completion condition.

Passive reads never touch presence or expire handoff leases. An expired lease
therefore retains its stored state until a canonical mutating action handles
it. Current authorization and event visibility still apply on every read.
Participant preparation, MCP negotiation/discovery and receipt lookup also
authenticate against current storage without updating presence. A cached
credential cannot keep these reads authorized after revocation.
The observer needs `events.read` for its cursor/long-poll and canonical access
to the handoff. A missing permission is a refusal; this command never grants it.
Servers without the passive contract are refused; no active-read fallback is
used. Long-polls are bounded to 30 seconds with finite transport deadlines.
The observation timeout is checked after canonical reads; bounded preflight
and final-read network time can extend wall-clock duration.

`handoff create --wait` also observes its original pending approval by reference,
then waits for the resulting handoff. It checks support for passive observation
before creating work. If observation fails after creation is confirmed, the
output retains the confirmed creation and its IDs. Timeout or Ctrl+C stops only this observer.
It does not answer, cancel, recreate or complete work. The participant profile
lock is released before waiting, and no SQLite transaction spans a network wait.

## JSON and exit codes

Outputs have `format: 1`, `state`, `exit_code`, and `possible_effect`, with the
recoverable request/handoff IDs and scope when available. Creation states refer
to canonical creation or approval, not execution completion. `possible_effect`
marks unresolved productive effects; an observational network failure can be
uncertain while having `possible_effect=false`. Results are printed, not saved
as a local conversation store.

| Code | Meaning |
| --- | --- |
| `0` | Confirmed creation/pending approval, completed inspection, or completed handoff |
| `2` | Invalid command syntax or argument combination |
| `3` | Known refusal, conflict, incompatibility, expired replay, or rejected/cancelled work |
| `4` | Observation timed out; work was not cancelled |
| `5` | Outcome/reference could not be confirmed; recover or review the same ID |
| `130` | Interrupted observer/command; retain its request checkpoint |

Argparse usage errors keep its established stderr format and code `2`; they
do not produce a successful JSON envelope. Existing `work` codes are unchanged.
