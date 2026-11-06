# PR-05 — terminal coordination, durable recovery and passive observation

Date: 2026-11-06. Platform: Windows 11. Nexus 0.3.3 on `feature/v0.3.3`.
Connector 0.0.12 and Core 0.0.14 are unchanged in this increment.

## Delivered contract

`message send`, `handoff create`, `handoff wait`, and `request inspect` use an
existing participant profile and its currently authenticated actor/workspace.
The reusable synchronous facade talks directly to canonical MCP through the
existing SDK. It does not access Server tables, select an actor through `--to`,
open a canonical session, convert routing, or decide an approval. Explicit
session context survives recovery; session proof must be supplied again.
Handoff visibility preserves the canonical private/eligible/public values.

Before transmission, protected local files retain the request ID, scope,
semantic digest, original local/Server deadlines and non-secret session context.
They contain no message body, handoff result, API key or session proof. A failed
pre-transmission write sends no productive call. Uncertain transmission or a
post-commit checkpoint failure retains the same ID. Reopening first looks up
the original receipt and does not resubmit a confirmed object/approval.
An absent receipt permits an explicitly resumed same-ID request only within
both original 30-day windows. Backward clocks, expired windows and missing
previously confirmed receipts refuse replay. `--new-request` explicitly starts
new work; timeout never generates a replacement ID. Old Servers fail discovery
before a productive call. Runtime validation also remains active under Python
optimization (`-O`).

Completion observation captures a cursor before the first canonical handoff
snapshot, uses bounded passive long-poll, then rereads the exact handoff even
when completion events are hidden from its creator. VERIFYING is nonterminal;
delivered/read messages and native idle do not complete a handoff. Pending
approval observation follows the original request without deciding or resending
it. Timeout and Ctrl+C leave work untouched. A failure after confirmed creation
retains the creation reference in output. JSON format 1 and exit codes are
documented in `docs/terminal-coordination.md`.

Passive service reads skip presence and lease expiry. Every page and final
timeout rechecks current key/capability/method/visibility permission. The HTTP
boundary now authenticates participant preparation, MCP transport/discovery,
receipt lookup and explicitly passive tools through a fresh read transaction,
without consulting/populating a positive auth cache or updating `last_seen_at`.
Other operations retain ordinary activity behavior. There is no generic header
that skips authentication or suppresses activity for arbitrary tools.

## Qualification and corrected findings

Installed qualification covers **614 distinct passing test cases**, with one
optional tokenizer measurement skipped. The overlapping runs are:

| Report suffix (`pr05-coordination-cli-…`) | Result |
| --- | --- |
| `behavior-installed.xml` | 139 passed: facade, passive services/HTTP, CLI |
| `transport-auth-installed.xml` | 145 passed: MCP, doctor, auth/cache/operator, HTTP and managed capabilities |
| `regression-installed.xml` | 325 passed; two old HTTP-envelope expectations failed initially |
| `release-installed.xml` | 42 passed: all 34 CLI cases, passive HTTP and import boundaries |
| `revocation-installed.xml` | Both initially failed cases passed with strict HTTP and stale-context checks |
| `surface-installed.xml` | Reduction gate passed; optional tokenizer measurement skipped |

The final wheel SHA-256 is
`1bd3360cc050cba59fb440aa04c55e8726e25a01d769278ebe977b60b39e944e`.
It contains 457 Python files, seven static assets and 160 migrations, all
compared byte for byte with source. The broad qualification wheel was
`e80c5869b0760244a28fe63f5567704df19f8bf8920ded700239d66c0cdf89d6`;
only the CLI profile-directory guard changed before the final wheel. The
release-scope report proves all other package payloads are identical. The
earlier unqualified pre-auth-fix candidate is retained as `wheel-initial.json`.
Validation ran outside the checkout in fresh installed environments; dependency
checking passed for all 46 installed packages. The installed-summary report
counts unique test identities and records no unresolved failures.

The source campaigns found and corrected:

- A failed local checkpoint was initially reported as a possible productive
  effect even though no call occurred. It now reports a known pre-call refusal.
- A created receipt without a canonical resource ID was initially accepted.
  Receipt validation now requires the reference appropriate to its state.
- Generic DB/INTERNAL errors after a productive call could occur after commit.
  The transport now preserves uncertainty for these outcomes.
- Service-only passive tests missed HTTP authentication's presence write.
  Strict CLI snapshots including every `agents` field exposed the issue. The
  new TCP suite covers cold/warm cache, discovery, reads, key rotation/revocation,
  legacy productive activity, and attempts to spoof the passive classifier.
  The previous milestone's no-heartbeat claim was qualified only at the service
  boundary; this increment corrects the HTTP boundary.
- Python `-O` removed assertion-based runtime checks. A real optimized process
  reproduced acceptance of an incomplete Server contract; explicit checks now
  reject invalid checkpoints, contracts and substituted receipt references.
- The CLI initially offered a noncanonical visibility value. It now exposes
  private/eligible/public; TCP tests verify the stored value and reject workspace
  as an argument error before Server effects.
- Coordination initially lacked the participant directory/link/ACL check used
  by launch and doctor. It now reuses that protection before lock acquisition,
  profile reads or credential access. Two targeted boundary simulations verify
  the order of refusal; they do not qualify a new native ACL implementation.

Initial reports are retained. Fixture corrections include a misplaced test
assertion, observation fault injection whose one-second budget expired before
the injected call, use of a nonexistent `python -m okto_nexus` entrypoint, and a
synthetic post-commit error accidentally echoing the fixture key. The real
process test now uses the installed console entrypoint: process death after
commit, recovery in a second process and inspection in a third retain one
canonical object and do not change presence. These fixture corrections did not
weaken product assertions. `pr05-coordination-cli-source-reports.json` maps
original source reports and any synthetic-key redactions.
Trailing whitespace in XML failure text is represented by character entities;
parsed XML content is unchanged by this formatting normalization.

The installed broad regression exposed two old tests whose helper required
HTTP 200 before checking a revoked key's tool-level refusal. Fresh passive
authentication now rejects at HTTP 401 before tool dispatch. Both tests now
assert that boundary and additionally pass a stale pre-rotation context directly
to the receipt service to retain independent transaction-level authorization
coverage. Both passed on the unchanged final wheel. The original failed report
is preserved with six synthetic fixture-key occurrences redacted and recorded
in `pr05-coordination-cli-regression-redactions.json`.

## Scope and limits

HTTP, MCP, SQLite, filesystem checkpoints, process death and console recovery
are real in isolated fixtures. Provider/native execution peers are synthetic;
no personal vault, client configuration, service registration or provider
inference was used. This is not the two-client cooperation campaign or real
productive local/remote M1 acceptance. DX-08, qualified external-client
cooperation, native service campaigns and the wider R3 plan remain open.

Observation requires `events.read` and canonical access to the handoff. Missing
authority is a refusal; there is no permission grant or active-read fallback.
Each long-poll is capped at 30 seconds; bounded preparation/final reads may
extend wall-clock duration beyond the selected observation timeout. No database
transaction is held across network waiting. No external exactly-once guarantee
is claimed beyond the documented canonical receipt contract.

Discovery revisions and extended MCP docs are updated. The existing surface
growth ledger records exactly 681 additional resident characters for the
workspace/passive fields. Baseline, divisor and the 40% reduction threshold are
unchanged. The fixed R3 source and ID sets are unchanged.
The measured default surface includes harness tools and excludes experimental
memory; using those same presence flags as the existing gate gives a reduction
of 40.1298%. The surface report also records the helper's value without those
flags so the configuration is explicit.
