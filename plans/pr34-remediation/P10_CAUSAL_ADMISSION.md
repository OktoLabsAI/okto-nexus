# P10 — persistent causal admission (partial milestone)

Date: 2026-09-23. Parent SHA: `cb59f18` on `feature/v0.2.0`.
The commit containing this document identifies the tested implementation.
PR34 rechecked with `rtk proxy gh pr view 34 --repo OktoLabsAI/okto-nexus --json headRefOid,baseRefOid,state,headRefName`:
OPEN, head `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`, base
`27b06fe48b9f95b35c94f50827fea83d178f4e12`; no newer PR changes to preserve.

## Implementation and contract mapping

- Migration 050 adds `runtime_causal_roots` and `runtime_message_causality`.
  These are the logical root/parent/budget contract; existing inbox/outbox remain
  the delivery and attempt authorities. Roots snapshot limits and deadline.
- `RuntimeCausalityService.record/reserve_execution/validate_dispatch` perform
  transactional admission. Canonical message parent and authenticated context
  determine lineage, never model text, tracing or last-session state. A sender
  must own or receive its parent. Atomic updates reserve child and execution
  quotas in the message/outbox transaction; rejection rolls back the whole child.
- `MessageService`, `RuntimeDeliveryPlanner` and `RuntimeWorkService` wire this
  into production composition. Dispatcher checks deadline before native effects.
  Existing managed-work creator/claim/grant authority remains mandatory.
- A correlated result inherits the original operation's message root as an
  observation, even after deadline. This does not authorize a new execution.
- `NexusConfig` exposes bounded operator settings: depth 4, generated messages
  32, executions 16, deadline 1800 seconds; new-root quotas 32/agent/minute and
  128/workspace/minute. Generated-message count excludes the authenticated root
  entry and nonexecuting observations; executable generated children will need
  reservation in the next relay unit. Existing roots retain their snapshots.
- `SqliteMessageRepo`/`SqliteMessageDeliveryRepo` retention excludes outbox,
  result-publication and causal references from both dry-run and deletion. Normal
  unrelated history still expires. Evidence/fences have no age-only deletion.
- Legacy supervisor TTL callback now rejects an expired chain instead of minting
  a new one. Production dispatch uses the persisted causal service, not callback
  state. Legacy unauthenticated inbox messages do not acquire runtime authority.

## Commands and observed evidence

All tests use isolated temporary stores and synthetic peers; no model/provider
calls in this milestone. Counts below are separate runs, not additive coverage.

1. Prior unit on parent: corrected `test_authenticated_reply_inherits_root_instead_of_starting_a_new_budget`
   was RED (1 failed, 3.62s): distinct roots for an explicit reply. First authoring
   attempt lacked required subject (1 failed, 3.57s), not behavioral evidence.
2. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_causality.py tests/test_pr34_remediation.py -k 'inherits_root or expired_relay' -x`
   — 2 PASS, 35 deselected, 6.19s (before expanded tests).
3. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_causality.py -k retention -x`
   — first test authoring error: absent workspace field (1 failed, 4.45s).
   Corrected test reproduced retention selecting protected runtime rows
   (1 failed, 4.73s); expected ordinary count subsequently includes the canonical
   receipt as well as the explicit unrelated fixture.
4. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_causality.py tests/test_retention.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_result_publication.py`
   — 60 PASS, 107.11s. Concurrent last-message/last-execution budget races, rollback,
   expired roots/new entries, retention, canonical work and result publication.
5. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_causality.py`
   — 15 PASS, 27.42s after adding late output, configuration and root-rate quotas.
6. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_causality.py -k slow_chain -x`
   — 1 PASS, 15 deselected, 2.61s. Clock advances 10/20/30 minutes; fresh bootstrap
   opens the same store between hops, preserving root/deadline. This is a fresh
   composition test, not a serve-process crash/restart campaign.
7. `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_causality.py tests/test_retention.py`
   — Linux 45 PASS, 46.54s, includes all 16 causal tests.
8. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_pr34_remediation.py tests/test_config.py`
   — 84 PASS / 5 FAIL, 61.70s. Five older tests assumed synchronous send after
   admission, contrary to the already implemented durable command contract.
   Updated them to await actual peer send (bounded helper), without weakening
   exactly-one assertion. Focused `-k enabled_authorized` before fix: 1 FAIL,
   4.32s; after: 4 PASS, 32 deselected, 12.17s. Focused
   `-k additional_adapter_through`: 1 PASS, 35 deselected, 3.94s.
9. `rtk proxy ruff check src/okto_nexus/application/runtime_causality.py src/okto_nexus/application/runtime_delivery.py src/okto_nexus/application/runtime_work.py src/okto_nexus/application/messages.py src/okto_nexus/application/retention.py src/okto_nexus/application/harness_supervisor.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/adapters/outbound/sqlite/messages_repo.py src/okto_nexus/config.py tests/test_runtime_causality.py`
   — PASS.

## Operation, recovery and remaining gate

Apply migration through the normal forward runner. No personal store was migrated.
Retain causal and outbox rows with backup/restore; do not delete them to refill a
budget or retry an uncertain attempt. Deadline affects new admission, not captured
results or already accepted work. Start an explicitly authenticated independent
conversation after expiry, subject to actor/workspace rate quotas.

P10 is IN_PROGRESS, not complete. Next: explicitly authorized result relay and
notify-target configuration, durable nonrecursive relay-block reasons, self-loop
defense, interleaved roots/endpoints and full process-restart/fanout coverage.
Current result observations deliberately remain nonexecuting until that unit is
integrated. Managed claims currently begin roots; any derived-work causal link
must be established through canonical authority, not model-supplied IDs.
P11/P12, aggregate matrix, build and reinstall remain pending. Native P10 Codex,
Claude, Pi and attach tests are NOT_RUN; prior P09 real results are not reused as
P10 evidence. Final gate NOT PASSED.
