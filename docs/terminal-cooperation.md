# Optional cooperation check

`participant smoke` tests a directed exchange between two existing identities,
then offers a separately consented handoff. It uses the existing participant
profile and the Server's canonical coordination tools. It does not start a
client, service or model, create an identity/session, change permissions, or
claim/complete work on behalf of the peer. A configured recipient runtime may
execute in response to the message or handoff, consuming capacity and provider
budget; each review states that effect before submission.

The result proves the observed cooperation between identities. It does not
identify which of several clients sharing a key participated, establish that a
model called a tool, or qualify all runtime behavior. The existing managed
connection test and its `NEXUS_CONNECTION_OK` marker keep their original meaning.

## Review and consent

```sh
okto-nexus participant smoke exchange --profile author --to reviewer --plan --json
okto-nexus participant smoke exchange --profile author --approve EXCHANGE_REVISION --json
okto-nexus participant smoke observe --profile author --timeout 300 --json

okto-nexus participant smoke handoff --profile author --plan --json
okto-nexus participant smoke handoff --profile author --approve HANDOFF_REVISION --json
okto-nexus participant smoke observe --profile author --timeout 300 --json
```

The exchange review names the Server installation/origin, authenticated-profile
identity, workspace, exact peer, request ID, proposed message and possible
effects. A new review saves only local metadata and does not read credentials
or contact the Server. Submission authenticates the current profile and checks
the installed Server's durable-request, passive-observation and correlated-reply
contracts before sending anything. An older Server is explicitly refused.

The peer must be a different identity. A message is always directed to that peer;
there is no broadcast conversion. The generated message asks for an optional
canonical reply to its incoming `message_id`, addressed directly to the author,
with a dedicated `client_request_id`. The observer checks parent, author, target,
workspace and actual delivery. It reads metadata without pulling or acknowledging
the inbox, including replies another session has already read.

The handoff review becomes available only after a current canonical reply is
confirmed. Creating it requires a different review revision and consent. The
message's approval cannot authorize the handoff. The handoff asks the peer to
claim that exact work and submit a non-null result for the same claim generation,
without changing files or starting unrelated work. Existing Server approvals
and execution policies still apply; the initiating participant cannot decide an
approval on behalf of an operator.

In an interactive terminal, omit `--plan` to see the review and answer its
confirmation. JSON/noninteractive review never implies consent. Once a phase's
consent is saved, repeating `exchange` or `handoff` resumes that same phase
without asking for approval again. `--plan` always shows a review without sending.

## What counts as evidence

A reply qualifies when the Server confirms its correlated authenticated
coordination receipt, or a canonical successful native-runtime publication.
Legacy messages with an unverified declared author do not qualify. Native
publications marked failed/interrupted do not pass the exchange merely because
they exist. No response text, trace string, delivery/read receipt or marker is
treated as the proof. The query filters the expected parent/peer/scope before its
fixed 50-reference limit and places confirmed evidence before unconfirmed noise;
`replies_truncated` makes truncation explicit.

Handoff proof requires the exact handoff, creator/workspace/direct peer, that
peer as claimant, a positive `claim_epoch`, canonical `COMPLETED` state and a
non-null result. `OPEN`, `CLAIMED` and `VERIFYING` do not pass. The observer can
recover completion that happened before it began waiting. It captures a cursor
before the first snapshot and rereads canonical state after bounded long-polls,
including when no relevant event is visible. Events only trigger a reread.

Observation requires the participant's current MCP authorization and
`events.read`. It does not keep the agent alive, renew a lease, consume messages,
approve, claim, cancel or complete work. Timeout and Ctrl+C stop only observation.
The profile lock is released before waiting; a separate attempt lock serializes
its local evidence updates without blocking ordinary coordination commands.

## Recovery and historical inspection

```sh
okto-nexus participant smoke status --profile author --json
okto-nexus participant smoke observe --profile author --attempt SMOKE_ID --timeout 30 --json
okto-nexus participant smoke exchange --profile author --attempt SMOKE_ID --json
okto-nexus participant smoke exchange --profile author --to reviewer --new --plan --json
```

Every attempt has its own smoke ID and distinct message/handoff request IDs.
Before a productive call, the ordinary coordination facade writes its durable
request checkpoint. Response loss or process death recovers those same IDs;
neither timeout nor a missing result creates a replacement. The original local
and Server replay windows remain fixed. Expiry, changed scope/profile/session,
missing confirmed receipts and backward clocks retain their ordinary refusals.
If authentication later fails while an earlier submission remains uncertain,
the output preserves that uncertainty and its IDs.
If an already-consented phase loses its request checkpoint, resuming permits
only receipt inspection. It cannot initialize another replay window, even when
the local smoke journal never received the original response. A missing Server
receipt remains uncertain and does not authorize recreating that request.

`--new` explicitly starts a separate review; it does not cancel the old attempt.
`--attempt` selects an older retained attempt. Observing an older attempt does
not change which review the latest index selects. Missing/corrupt indexes and
checkpoints require inspection; the command does not repair them by resubmitting.

Files live under `HOME/terminal/cooperation/PROFILE/attempts/HASH/`, separate from
the latest request of ordinary `message send` and `handoff create`. The local
record stores scope/profile hashes, IDs, review/consent digests, canonical
references and observation timestamps. Message bodies, result text, keys and
session proofs are not saved there. Optional `--session-id` preserves an existing
session; supply its proof at submission via `--session-secret-env NAME` when
required. Credentials use the existing protected profile, `--key-stdin`, or the
explicitly selected `--key-env NAME`; no operator credential fallback is used.

`status` and retained `--plan` are local snapshots: no key lookup, network,
repair or lock-file creation. They remain readable while another process
observes the same attempt. Their `historical: true` label is material. Creating
the first handoff review reads current Server evidence; saved handoff reviews
are displayed locally, and submission revalidates the evidence before an effect.

Participant doctor may display these references as
`UNKNOWN/HISTORICAL_EVIDENCE_ONLY`, with `source=local_receipt` and a separate
`last_observed_status`. It does not turn retained evidence into a current check.
Client reload, the harness environment and productive work remain independent
levels. A later `observe` can refresh the same attempt explicitly; loss of old
message evidence does not prevent observing an already-created handoff.
If a current observation cannot revalidate old proof, its check is `UNKNOWN`;
the older evidence remains available separately through historical `status`.

## JSON and exits

Format 1 output separates `coordination_participation` and `handoff_test`, includes
recoverable IDs and `qualification: identities_only`, and distinguishes stored
evidence from a current observation. An exchange may pass while the handoff is
still unrequested. After an error, the retained `smoke` snapshot accompanies the
error when available; it does not erase a creation that already committed.

Codes follow [terminal coordination](terminal-coordination.md): `0` for a
confirmed command/review or proven stage, `2` for usage, `3` for known refusal,
`4` for observation timeout, `5` for uncertainty, and `130` for interruption.
An observational failure can be uncertain without creating any new effect.
The maximum selected observation window is 86400 seconds; each long-poll is at
most 30 seconds, and bounded preparation/final reads can extend wall-clock time.
