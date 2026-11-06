# PR-03/PR-04 — optional canonical cooperation smoke

DX-08 is implemented as `okto-nexus participant smoke exchange|handoff|observe|status`.
The existing participant profile supplies the identity and scope. A local exchange
review discloses the exact directed message, recipient and potential runtime/provider
cost. A separate handoff review and consent are available only after a canonical
peer reply. The command does not start a client, create an identity/session, alter
permissions or act for the peer. Existing Server approval policies remain in force.

## Evidence and recovery contract

`message_status(include_replies=True)` is an authenticated passive metadata query.
It checks the original sender and managed workspace, and filters replies by exact
parent, workspace, peer, direct recipient and actual delivery before its fixed
50-reference limit. Replies already consumed by another session remain observable.
Only authenticated coordination receipts or successful canonical native publications
qualify. Legacy declared senders and failed/interrupted native publications do not.
No body, model response marker or trace text is used as proof. Native provenance
joins the canonical result and delivery generation; duplicate publications prefer
successful evidence. No new database migration is introduced.

Handoff proof requires the exact creator/workspace/direct target, peer claimant,
positive claim generation, COMPLETED state and non-null result. Event cursors are
captured before snapshots; events trigger canonical rereads rather than deciding
success. Empty/invisible event pages, approvals and completion before observation
are covered. Timeout or observer exit cannot claim, complete, cancel or resend work.

Each attempt has distinct durable message/handoff request IDs, private metadata-only
journals and the existing fixed replay windows. Lost responses, failed confirmation
writes and actual process death recover the same IDs. A previously consented phase
whose request checkpoint disappears permits only receipt inspection, even when
the smoke journal never received a response. Missing receipts remain uncertain;
the command cannot initialize another window after pruning. Authentication failure
preserves this uncertainty. A proven failure before the first consent/checkpoint
write remains a known refusal without productive effects.

Historical status and retained plans do not acquire/create guards, read credentials,
contact the Server or write state; they work while another observer holds its lock.
Observation holds an attempt lock and releases the shared profile lock. Observing
an older attempt cannot replace the latest review index. Doctor displays retained
proof as UNKNOWN/HISTORICAL_EVIDENCE_ONLY, separate from current checks. Current
observation returns UNKNOWN when old evidence cannot be revalidated; historical
status retains that evidence and its observation time.

## Installed validation

**440 distinct test cases passed**, with one manual A/B assertiveness campaign
skipped. The skip is the existing two-harness probabilistic campaign, not a missing
tokenizer. Validation ran with Python `-I` outside the checkout in fresh wheel
environments. The installed summary replaces superseded facade/CLI cases instead
of adding overlapping reruns to the total.

| Report (`pr04-cooperation-…`) | Result |
| --- | --- |
| `behavior-installed.xml` | Initial candidate: 150 passed |
| `coordination-installed.xml` | 165 passed: existing facade, MCP transport, CLI and doctor |
| `server-installed.xml` | 116 passed, 1 manual skip: inbox, authorization, provenance, schema, surface and architecture |
| `facade-cli-installed.xml` | 142 passed; initial uncertainty-classification fix exposed one pre-consent refusal regression |
| `release-boundaries-installed.xml` | All 3 affected cases passed on the final wheel |

The initial candidate passed its then-existing tests; subsequent independent review
found lost-checkpoint replay-window renewal and stale PASS projection. The facade
fixes passed 33 focused source cases and all 113 installed facade cases. A real TCP
regression reproduced loss of the uncertainty flag after checkpoint deletion and
key revocation. Its first correction was too broad for a failed initial consent
write. The final CLI distinguishes a consent loaded before the command from an
unsaved first consent. Both revoked-key cases and the pre-consent refusal pass.

Other retained initial failures were two old surface/discovery expectations and
a Windows fixture that tried to read a locked guard file. Expectations now include
the new advertised contract; the guard fixture compares those bytes before/after
lock release and checks other files throughout. Neither correction weakens the
passivity/provenance assertions. All source and installed reports, including failed
runs, are retained with hashes in `pr04-cooperation-source-reports.json`.
XML trailing whitespace is represented by character entities with parsed content
preserved; any synthetic-key redactions are separately counted there.

Final wheel SHA-256: `bb9143f2181993d93ff78dba9d6a6536d9a2f20de3b602997e048474ce43307d`.
All **460 Python files, seven static assets and 160 migrations** match current
source bytes. Only `terminal_cooperation.py` and CLI `cooperation.py` differ from
the initial broad-qualified package; only the latter differs from the second
package. `release-scope.json` records the exact unchanged payloads. All 46 installed
dependencies are compatible. Ruff E9/F passes for every changed Python file.
A broader lint invocation found four pre-existing unused imports in unchanged
`mcp/tools/harness.py`; these were verified against HEAD and are outside this change.

The live resident surface grew exactly 128 characters for the optional parameter.
The existing growth ledger records DX-08 separately. Baseline 41595, divisor four
and the 40% gate remain unchanged; adjusted reduction is 40.1298% with harness
enabled and experimental memory absent. Discovery advertises the cooperation
contract separately; the existing observation contract keeps revision 1.

## Qualification limits

HTTP, MCP, SQLite, filesystem checks, process death and console recovery are real
in disposable fixtures. Peers and identities are synthetic. This establishes
`identities_only` cooperation, not which external client/model sharing a key acted.
The managed `NEXUS_CONNECTION_OK` test retains its original meaning. No provider
inference, personal credential, service registration or user client configuration
was used. Qualified external-client cooperation, productive M1/M2, native service
campaigns, other platforms and the wider fixed R3 plan remain open. Connector/Core
are unchanged. DX-08 belongs to PR-03/PR-04; PR-05 supplies shared coordination
dependencies and is not redefined by this increment.
