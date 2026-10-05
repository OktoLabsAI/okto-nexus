# Durable initial turns

## Behavior

A runtime.start request can include text. The opening semantic payload remains unchanged. Resolution stores a distinct child turn.submit intent with a stable operation ID and the exact initial text. Resolution alone creates neither an operation nor an outbox entry.

Opening admission atomically creates the child operation and its durable parent relation. Repeated admission recovers the same IDs. A start that reuses a compatible session creates only a child turn, not another opening. Operation views expose follow_up_operation_ids.

The dispatcher creates the child's outbox entry only after the session is READY with an ACTIVE lease and the latest opening receipt is SUBMITTED or SUCCEEDED. Before sending, it rechecks the latest opening receipt and native identity, alongside the existing binding, source, lease, generation and grant checks. Unknown, failed or cancelled opening outcomes cannot authorize the delayed child. The initial turn consumes the ordinary send budget exactly once.

Connector accepts --text on start and preserves the request through canonical Server admission. Child IDs appear in the opening operation response. The CLI does not run an independent client-side submit after open.

## Persistence

Migration 090 adds initial_turn_json to the intent journal and parent_operation_id to operations, with a scoped parent index. Prior intent rows retain their values and default to no initial turn; prior operations have no parent. Migration 088 through 090 and idempotent repeated application are covered.

## Verification

The installed artifact campaign and retained failures are recorded in test_runs_20261001_initial_turns.json. Tests cover deferred dispatch, repeat resolution/admission, conflicting text, encoded payload limits, reuse, revocation before send and changed parent outcomes at reservation and send. Parent-loss cases deliberately inject a changed durable projection while retaining stale READY to exercise both guards.

The public parsed Connector CLI journey uses actual loopback HTTP/WSS, a daemon-owned Core runtime and a synthetic native peer. Its additional prompt requires one additional grant budget unit; the fixture explicitly budgets that unit and checks total consumption. This is not real-provider acceptance of the new wheels.

## Remaining acceptance

This implements the initial-child criterion in NS05.04. It does not close M03/M04 or G0-G3. Full process/ownership observations, logs, retention, UI and the final provider/platform campaigns remain governed by DELIVERY_PLAN.md.
