# M05/M07 — Embedded event publication and restart replay

Status: partial integration; M05, M07 and G1 remain open.

Migration 085 records each local stream with its opening operation, binding and agent in the same transaction as the pre-effect receipt binding. The serve-owned maintenance loop reads finite Core journal snapshots and commits events through the existing canonical Nexus ingress and reducer. The embedded path verifies the current store owner and generation inside the ingress transaction and requires a registered local stream. The remote path retains its ticket/lane checks.

Each stream page has at most 128 events, 64 KiB per event and 768 KiB total payload. Stream enumeration uses pages of 128. Server watermarks advance only after the event transaction commits. Core acknowledgments follow that commit. If the Core ACK fails, the next publisher reapplies the durable Nexus watermark before reading another page. This also works after restart and after Core event compaction; the publisher never infers an ACK from an attempted write.

Startup recovers receipts, then pending stream events before considering dispatch. History-only readers do not construct runtimes or load providers. Reads are retained through observer cancellation and joined before host stores close. The existing conservative failure path returns the owner to RECOVERING and contains native work after publication failure. Retained journals and slot ledgers still require resource reconciliation before CONTROL_READY.

## Verification

The serve tests cover native event ingestion, a failed Core ACK after successful Nexus commit, applying that ACK from a reopened history host, stale-owner refusal, failed Server persistence followed by two real serve restarts, and no duplicate event or native opening. The source and installed regression also exercise the existing remote event ingress. Native execution and contract qualification use technical fixtures.

Initial directed tests used an invalid technical event category (output); the fixture was corrected to the contract category text_delta. Those failures do not represent production contract acceptance. Final installed results, package hashes and raw evidence are recorded separately in test_runs_20260930_embedded_events.json.

Final installed results: 108 passed in the normal environment and 53 overlapping cases passed in the actual no-Connector environment, with pip check. Source regression: 33 passed. Both installed environments verified source/wheel/installed bytes before execution.

## Remaining fixed-plan work

Resource/slot reconciliation and readiness after retained-store recovery; complete public event/history/UI consumption; approvals/input; tools/vault; retention and pressure/platform qualification; and complete real Pi/Codex/Claude journeys remain required. This increment does not close a milestone or release gate.

Core and Connector artifacts are unchanged. Preexisting user UI bytes are included in the Nexus wheel but excluded from this commit and UI acceptance. The existing Starlette/httpx deprecation warning remains.
