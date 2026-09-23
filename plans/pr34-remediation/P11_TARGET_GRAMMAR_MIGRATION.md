# P11 — migrate legacy target-routing coverage

Parent `cacf6d3`, feature/v0.2.0, 2026-09-23. Only tests and execution documentation
change; production identity and transport contracts are not relaxed. Schema054,
surface42 and identity9 unchanged. Final gate NOT PASSED.

The fresh suite inventory reproduced ten failures before its maxfail boundary.
tests/test_harness_target_grammar.py still built the retired synchronous callback
composition and expected runtime open to register its Agent. The replacement uses
the existing authenticated production HTTP/MCP fixture with canonical identities,
operator-approved profiles/endpoints and the real dispatcher/journal. Only the
external peer is synthetic. Capability and tag catalogs are registered through
their public REST APIs. Five routing strategies inspect one real native command,
the full untrusted canonical envelope, durable attempt and exclusive inbox
reservation. Failure isolation keeps the original uncertain attempt and blocks a
second native write while still committing a second logical message.

## Coverage migration map

Old names below are from the parent file; mappings identify executable current
coverage, not removed requirements.

| Previous case | Current evidence |
|---|---|
| direct, capability, role, tag target reaches connector (four cases) | test_target_reaches_one_canonical_executor_with_full_envelope, five parameters including broadcast |
| forward_failure_does_not_wedge_the_session | test_failed_transport_preserves_durable_delivery_and_blocks_duplicate_lane; uncertainty deliberately retains lane instead of blindly sending a second turn |
| send_only_connector_still_rejects_steer_directly | test_correlated_relay_can_reach_send_only_target_without_inventing_a_reply rejects operator steer and proves no extra wire command |
| forward_to_a_send_only_connector_only_ever_issues_send_turn | test_send_only_target_keeps_write_distinct_from_ack |
| delivery_row_is_unaffected_by_forward_outcome_either_way | routing/failure tests retain unread logical delivery with exclusive push reservation; test_runtime_outbox.test_p05_reserved_push_delivery_cannot_also_be_claimed_or_acked_by_pull proves exclusivity; test_runtime_result_correlation tests actual correlated consumption |
| harness_to_harness_relay_succeeds_for_a_single_legitimate_hop | test_runtime_relay.test_explicit_three_agent_chain_preserves_initiator_and_budget plus send-only relay case |
| runaway_harness_to_harness_cascade_is_stopped_and_observable | test_runtime_relay.test_bidirectional_relay_stops_at_persistent_depth_and_keeps_result (three protocol peers, durable blocked decision) |
| slow_paced_harness_to_harness_cascade_is_still_stopped | test_runtime_causality.test_slow_chain_keeps_original_deadline_across_fresh_composition and test_runtime_relay_process_restart.test_slow_canonical_chain_keeps_deadline_across_four_server_processes |
| new_conversation_between_same_pair_long_after_an_earlier_finished_chain_is_not_blocked | test_runtime_causality.test_expired_root_rejects_continuation_but_allows_explicit_new_entry; interleaved-root test in test_runtime_relay |
| relay_from_another_live_harness_into_a_send_only_connector_only_ever_issues_send_turn | new test_correlated_relay_can_reach_send_only_target_without_inventing_a_reply: actual Codex JSON-RPC fixture origin and approved fake attach destination, same root, one result only |
| self_addressed_direct_message_does_not_loop | test_runtime_relay.test_self_loop_is_recorded_without_starting_another_turn |
| real_composition_root_wires_the_shared_notifier | every new routing case runs production serve/MCP/REST/dispatcher composition; test_runtime_outbox additionally proves authenticated stdio producer/owner paths. The removed callback itself is no longer the contract |

The legacy assertion that forwarding never reserves/consumes inbox contradicts
the accepted remediation. Native transport write still does not consume it, but
exclusive reservation and correlated result processing are required. Likewise a
fresh uncorrelated terminal cannot initiate an authorized new relay root, and an
elapsed TTL cannot renew a continuing chain. The mappings preserve the intended
delivery/loop guarantees using current contracts rather than restore those bugs.

## Execution

- Initial migrated file, `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_harness_target_grammar.py -x`:
  1 FAIL in3.53s because fixture assertion tried parsing the untrusted-data banner
  as JSON. Assertion now checks the banner and parses the following JSON.
- Same file without `-x`: 1 FAIL,6 PASS in15.26s. Capability name was missing from
  the required canonical catalog. Fixture now explicitly registers it over REST.
  Neither failure was a new production defect or a reason to weaken validation.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_harness_target_grammar.py -k send_only`:
  **2 PASS**,6 deselected,9.31s; includes actual native-protocol origin and fake
  send-only destination. This is not a real Claude attach session campaign.
- `rtk proxy ruff check tests/test_harness_target_grammar.py`: **PASS**.

Real provider/model runs for this unit: **NOT_RUN**. Pi and dedicated Claude
attach native remain NOT_RUN. Mapped process-crash/correlation tests retain their
previous scoped evidence until rerun; mappings alone do not claim a fresh pass.

Integrated selections:

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_harness_target_grammar.py tests/test_runtime_relay.py tests/test_runtime_causality.py tests/test_runtime_outbox.py`: **60 PASS**,144.25s (before the added relay-to-send-only case).
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_harness_target_grammar.py tests/test_runtime_relay.py tests/test_runtime_causality.py`: **47 PASS**,147.76s, including the added case.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_harness_target_grammar.py -k correlated_relay`: **1 PASS**,7 deselected,7.68s after strengthening the steer rejection to require VALIDATION_ERROR, not just any failure.
