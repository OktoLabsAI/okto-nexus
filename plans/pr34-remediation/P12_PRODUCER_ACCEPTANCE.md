# P12 — all canonical message producers

Parent `3b7eb2cbec0222ee14d6e92827dd4ed844004cb4` plus new REST producer test hash in `evidence/p12-producers-index.json`. Production unchanged.

T-TX-06 joins exact existing assertions and new REST coverage, all rerun on this source:

- MCP message creation: four failure cuts after actual message/delivery/outbox/event writes roll back the complete canonical set, then a fresh request succeeds once.
- REST steering: authenticated operator route writes the same message, logical delivery and reserved transport operation in one UoW. Failure after real outbox insertion rolls all three and events/causality back. Both normal and recovered requests produce exactly one peer send, with authenticated operator identity.
- Synthetic handoff execution: actual failure after outbox insertion rolls back claim, message, intent and grant charge; retry is admitted. The canonical work flow/coalescence itself remains additionally qualified by P12_WORK_ACCEPTANCE.md.
- Approval executor: pending HITL has no message/intent/turn; three concurrent approval decisions plus a subsequent repeat produce one canonical operation/native result, as in P12_APPROVAL_ACCEPTANCE.md.
- Result projector/publication: actual finish followed by a failure rolls back publication and its canonical message; wake retries to one publication. This is the existing canonical publication transaction, not a nested independent writer.
- Independent stdio writer: actual Nexus subprocess commits canonical message/intent and wakes the existing serve owner without owning/spawning a competing runtime.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_rest_producer.py tests/test_runtime_delivery_acceptance.py::test_each_canonical_write_rolls_back_without_orphan_intent tests/test_runtime_handoff_dispatch.py::test_managed_claim_commit_cut_rolls_back_claim_delivery_and_grant tests/test_runtime_result_publication.py::test_publication_and_canonical_message_commit_together tests/test_runtime_approval_acceptance.py tests/test_runtime_outbox.py::test_p06_stdio_producer_wakes_serve_without_owning_runtime -q --junitxml=.git/pr34-evidence/producers-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_rest_producer.py tests/test_runtime_delivery_acceptance.py::test_each_canonical_write_rolls_back_without_orphan_intent tests/test_runtime_handoff_dispatch.py::test_managed_claim_commit_cut_rolls_back_claim_delivery_and_grant tests/test_runtime_result_publication.py::test_publication_and_canonical_message_commit_together tests/test_runtime_approval_acceptance.py tests/test_runtime_outbox.py::test_p06_stdio_producer_wakes_serve_without_owning_runtime -q --junitxml=.git/pr34-evidence/producers-linux.xml
rtk proxy ruff check tests/test_runtime_rest_producer.py
rtk git diff --check
```

Terminal exit0: Windows21831 **10 PASS87.58s**, Linux98256 **10 PASS121.58s**, no failures/skips. Ruff PASS. Per-node manifests in index; raw XML retained under .git/pr34-evidence. Synthetic transports/native protocol processes do not qualify a real provider campaign.

Original matrix121 PASS/8 NOT_RUN. Final gate NOT PASSED. Remaining: positive mirror observer, journal/storage exhaustion, external authenticated attach work, operation event/replay state, native E2E01/02, actual-composition final join and final report; then complete suites and release/reinstall0.2.0.
