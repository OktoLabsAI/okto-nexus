# P10 — remaining fixture matrix

Parent `e6983f2a62910a70fcda139ee31753b5be339210`, 2026-09-23,
`feature/v0.2.0`. Migration 052 unchanged. This unit strengthens existing
production-composition tests; it does not modify production relay behavior.

| Matrix case | Direct evidence |
|---|---|
| T-RELAY-04 | `test_interleaved_roots_share_sessions_without_sharing_budgets`: two roots on the same sessions, joined through exact result/operation/message parent, distinct counters |
| T-RELAY-06 | `test_concurrent_children_cannot_exceed_snapshotted_budget`: eight authenticated HTTP/MCP requests compete for the last message or execution budget; one succeeds and seven receive QUOTA_EXCEEDED; no failed reservation survives |
| T-RELAY-07 | `test_repeated_publication_does_not_charge_or_dispatch_again`: eight concurrent retries through the production message/result service return the existing child, with no additional budget or outbox row |
| T-RELAY-09 | `test_bidirectional_relay_stops_at_persistent_depth_and_keeps_result`: all three duplex protocol adapters emit three processing receipts and one durable relay-blocked event, with only three intended operations. Failure/interruption/unknown and approval-denial tests verify no error/denial-triggered extra turn |

Commands/results:

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py tests/test_runtime_causality.py -k "concurrent_children or repeated_publication or interleaved_roots"`: **4 PASS**, 35 deselected, 19.00s.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_relay.py tests/test_runtime_causality.py -k "concurrent_children or repeated_publication or interleaved_roots"`: **4 PASS**, 35 deselected, 21.90s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py tests/test_runtime_causality.py`: **39 PASS**, 107.35s, including added receipt assertions.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_relay.py tests/test_runtime_causality.py`: **39 PASS**, 118.61s.

Together with P10_PROCESS_RESTART.md and P10_NOTIFICATION_TARGETS.md, all eleven
P10 matrix rows now have passing scoped evidence. This does not certify real-model
relay, physical power loss, later platform/version negotiation or P12 end-to-end
gates. Native relay remains NOT_RUN; the overall P10 phase stays IN_PROGRESS and
the final gate NOT PASSED. Next dependency: finish P11 administration, safe
discovery/diagnostics and operation recovery, then aggregate/native P12 gates.
