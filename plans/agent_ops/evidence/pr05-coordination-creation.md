# PR-05 — canonical coordination creation and recovery

Canonical MCP message_create and handoff_create accept an optional durable client_request_id. Authenticated actor/workspace/operation scope and semantic hash return the original metadata reference, including pending approval, without new inbox/outbox/runtime admission or quota charge. coordination_request_get reads only the authenticated creator reference, with explicit managed capability and workspace authorization; current key/capability and creation permissions are rechecked. Approval execution preserves original authority/provenance and commits the object, receipt, result and granted event in the same canonical transaction. Persisted decision_revision fences stale execution and compensation against a later rejection/reapproval; repository compensation also preserves archive. Real process exits before and after canonical approval execution recover the same request. Schema 158/159-to-160 preserves existing data and receipt deadlines. 74 main source tests, 14 managed-source tests and a separate final four-case race suite passed (overlapping suites); 225 installed behavior tests passed outside the checkout. The final wheel after description compaction passed 53 installed surface/recovery tests with one optional tokenizer measurement skipped. Application/domain bytes are identical to the behavior-qualified wheel. The wheel has 453 Python files, seven static assets and 160 SQL resources matching source bytes. HTTP/MCP/SQLite are real; native execution peers are synthetic. CLI durable checkpoint/recovery/expiry refusal, correlated coordination wait, cooperation smoke and productive local/remote M1 remain open.

## Contract and implementation

- The optional ID selects a reference-only response; calls without an ID retain their previous response. Scope includes the Server installation, authenticated actor, logical workspace, operation and request ID. Different normalized content/context conflicts. No caller can select another actor for recovery.
- Current authentication, connection method and creation permissions precede replay. Verified session provenance remains bound to its workspace. Managed recovery needs an explicit capability action and its bound workspace; adding the tool does not expand existing capabilities. Lookup never heartbeats, creates work or returns message/handoff content.
- One canonical write transaction owns the message/handoff, inbox, event, runtime outbox/admission and coordination receipt. Canonical dispatch accounting still happens in dispatch. Replay does not create another admission/charge. Late receipt/event/result failures roll back the whole new transaction.
- Approval payload keeps the original authority/provenance and generated trace, but never the session secret or API key. Decision revision is transient executor context checked against a persisted generation, and absent from public MCP schemas. Repeated matching decisions resume an approved/null-result attempt. The result and granted event commit with the resource, preventing a post-commit failure from reverting it to pending.
- Deterministic races use the real approval service/repository and SQLite transactions with a fixed clock. Delayed execution/compensation cannot override a rejection or a later identical approval. The additional archived-row CAS guard is repository defense: the public archive endpoint already refuses an approved request still executing.
- Creation/recovery documents advertise a fixed 30-day window, tombstones, pending/rejected/archived/removed states, and uncertainty after receipt pruning. Creation metadata is not delivery or completion. Server support is discoverable in nexus_info, surface revision 66.

## Evidence

| Report | Tests | Failures | Errors | Skips |
| --- | ---: | ---: | ---: | ---: |
| `pr05-coordination-creation-installed-before-archive-fence.xml` | 224 | 1 | 0 | 0 |
| `pr05-coordination-creation-installed-concurrent-diagnostic.xml` | 2 | 0 | 0 | 0 |
| `pr05-coordination-creation-installed-transport-initial.xml` | 23 | 1 | 0 | 0 |
| `pr05-coordination-creation-installed.xml` | 225 | 0 | 0 | 0 |
| `pr05-coordination-creation-managed-source.xml` | 14 | 0 | 0 | 0 |
| `pr05-coordination-creation-races-final.xml` | 4 | 0 | 0 | 0 |
| `pr05-coordination-creation-release-installed.xml` | 54 | 0 | 0 | 1 |
| `pr05-coordination-creation-source-final.xml` | 74 | 0 | 0 | 0 |
| `pr05-coordination-creation-source-initial.xml` | 1 | 1 | 0 | 0 |
| `pr05-coordination-creation-source-second.xml` | 19 | 2 | 0 | 0 |
| `pr05-coordination-creation-source.xml` | 71 | 2 | 0 | 0 |
| `pr05-coordination-creation-surface-budget-initial.xml` | 8 | 2 | 0 | 1 |
| `pr05-coordination-creation-surface-initial.xml` | 37 | 1 | 0 | 0 |

Counts are per invocation and overlap. The initial source failure was an invalid test governance window (`hour` instead of `1h`). The second report expected HTTP401 where the application correctly returned a fresh-authentication denial in an HTTP200 MCP envelope. The 71-case report expected AUTH_FAILED for an invalid session proof; the canonical contract is NOT_OWNER. These were fixture/assertion corrections, not changes to weaken authentication. Initial managed-test expectations were also corrected for operation-specific authority prefixes and charging at dispatch. The review independently reproduced the approval race before the persisted-generation fix.

Both initial installed attempts encountered a Windows TCP reset in the handoff post-commit failure case: its deliberately unhandled ASGI exception sends a 500 and closes that connection, while the same client keepalive pool raced to reuse the closing socket for recovery. The standalone two-case diagnostic passed, confirming timing sensitivity. The test now isolates the deliberately failed decision in its own HTTP client and recovers on a fresh transport; it still requires the committed original reference and verifies one effect/event after concurrent decisions. No production retry or exception handler was changed for this fixture correction.

Surface checks then found an old exact nexus_info field set and two overlong descriptions. Cache-version/field expectations now match revision 66 and the descriptions are compact. The live previous wheel measured 35,658 cuttable characters; the final surface measures 36,200, a 542-character increase: recovery tool 307, two optional ID parameter descriptions 270, message description −35. The existing APPROVED_GROWTH ledger records exactly this DX-10 addition. Frozen baseline 41,595, divisor 4 and threshold 40% are unchanged; the adjusted reduction remains 40.1298%. No unrelated growth is discounted. One optional tiktoken measurement is skipped because that optional dependency is absent; the deterministic character metric is tested.

Two synthetic fixture-key appearances in the initial failed XML were redacted before committing evidence; failure text and counts are retained. No personal credentials were read for this campaign. Redaction counts from this recording: `{"pr05-coordination-creation-source-initial.xml": 2}`.

Installed invocations use clean temporary environments and `python -I -m pytest -c pytest.ini` from copied `nexus` directories. The behavior suites cover coordination creation/requests/races/managed, HITL, message delivery, first-use handoff, approval archive, migrations, retention, import boundary, canonical native approvals, terminal binding approval, handoff origins and MCP session capabilities. Only SQL fixtures are copied into src; imports resolve to site-packages. The release wheel differs from that behavior-qualified wheel only in three MCP tool description modules and the existing surface-metric ledger, as recorded byte for byte in the scope comparison. Its 53 passing tests cover all surface/schema/resource/budget suites plus real MCP concurrent creation, pending approval, expiry/discovery and all approval races. The optional tokenizer case is the single skip. Earlier reports remain as intermediate evidence.

Final wheel SHA-256: `8ca715e5c998cae137dfebc4731e5d207d44d0f949a6331dae0c77aa6cbe7569`. Python payloads: 453; static assets: 7; SQL resources: 160. Every shipped payload was compared byte for byte with the final source. [Wheel metadata](pr05-coordination-creation-wheel.json).

## Limits

This increment qualifies the canonical Server MCP and approval integration, including local process death and durable SQLite recovery. Synthetic native peers exercise delivery/admission/accounting; they do not qualify real model work or external exactly-once execution. No service registration, provider call, credential onboarding or productive local/remote M1 was performed. CLI request checkpoints, receipt-aware recovery after process restart, refusal to resend outside the known window, coordination wait and cooperation smoke are still required. DX-10, PR-05 and full R3 remain IN_PROGRESS. Connector/Core have no changes in this milestone.
