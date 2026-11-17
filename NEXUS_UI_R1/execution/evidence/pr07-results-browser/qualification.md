# Results follow-up and artifact correlation fix

All inputs are own historical SQLite facts plus three files created by the
actual artifact_upload use case. HTTP routes and browser rendering are real.
The synthetic terminal receipt rows do not form complete runtime receipt
histories: operation.read returns DB_ERROR / “Stored operation receipt history
is invalid.” This limitation was found and preserved before the fix. These are
not three native executions and no provider, model or personal login ran.

## Reproduced problem and final reader

before-fix-http-results.json shows one ui-handoff-0 result in VERIFYING with
only one artifact, despite three file-producing historical operations linked
to the same handoff claim (`a81d7d`). runtime_results permits one artifact ref
per canonical operation, so the first attempted fixture failed its UNIQUE
constraint when placing three refs on one operation (`198848`); it was corrected
to three correlated operations. A later fixture startup corrected a relative
source-pin path (`fc361e`). No production constraint was weakened.

Only src/okto_nexus/adapters/outbound/sqlite/home.py changed. The result reader
now materializes its existing authorized terminal-operation relation, including
current and historical delivery links; deduplicates artifact IDs by the same
logical result group and workspace; aggregates once; and attaches that array to
the existing selected result. It preserves the existing handoff/claim identity,
latest-terminal-receipt criteria, agent/workspace authorization filters, target,
view-state mechanism and cursor mechanism. It never groups by a display label.
There is no repeated sibling-artifact query for every operation.

The final two new HTTP/SQLite tests cover three files plus duplicate reference,
one logical result, unchanged identity/view-state, VERIFYING remaining intact,
other claim/project exclusion, global cross-workspace exclusion, a positive
historical delivery link and second executor, a latest nonterminal receipt
negative, and an agent-filter negative. With four existing related regression
cases, the final run is **6 PASS / 17.97 s** (`784e57`,
artifact-final-workspace-six-tests.xml). Earlier fixture/oracle failures remain
in their separate XML files. Initial test baselines lacked an execution_result
FK parent and confused the newly introduced tracking episode with a view-state
regression; both test defects were corrected, not product authority.

Artifact lists retain the existing DTO contract: bounded metadata strings, no
file content/path, and no invented silent list cap. This materializes/group-sorts
authorized refs under the existing SQLite query budget, not O(page) retrieval
or a memory-bound guarantee. There is no individual-artifact cursor. Old latency
measurements do not qualify this changed SQL.

## Scenarios and exact qualification cuts

- **T-RESULT-01 PASS at declared historical-fact scope:** final HTTP tests
  return three distinct authorized files in one result, not extra work items.
  Browser `116ba7` / completion `8455fc` verifies all three file names in the
  same real ResultRow. The final backend adds only the workspace-array fence
  after that browser run; its 6-case HTTP regression above is separate.
- **T-RESULT-02 PASS at the browser cut:** opening the result shows one panel,
  “Handoff awaiting verification”, “Submitted work is waiting for its canonical
  verification” and Verification: VERIFYING (`31dccc`). Viewing did not accept,
  acknowledge or complete the handoff: all selected business/receipt tables are
  byte-digest identical before and after. The historical session event stream
  is unavailable; that is explicit fixture history coverage, not a successful
  native viewer claim. The first case-sensitive label probe timed out
  (`b94bc5`); a case-insensitive exact-state inspection fixed the oracle.
- **T-RESULT-03 full scenario NOT_RUN:** real browser Mark seen uses one
  canonical revisioned preference POST and returns preference revision 1
  (`77ffa3`). Only attention_preferences changes (0→1); no business ACK occurs.
  Publishing a new canonical result revision/episode was not executed, so
  preference carry-over to a new episode is not promoted as PASS.
- **T-RESULT-04 PASS at the browser cut:** an actual first HTTP page has six
  results/has_more with limit 1; a different registered project has its own
  result. Opening Home, expanding/paging previews and opening a result cause
  zero POSTs and no preference/receipt/watermark mutation. The legacy browser
  operator-seen watermark remains null (`6355e7`). Only the later explicit
  Mark seen changes exactly one preference.
- **T-RESULT-05 PASS at the browser cut:** ui-untracked has view_state
  not_tracked and its real ResultRow says “Recent · seen state not tracked”.
  final-relation/summary.json reports unseen_results.value=null,
  total_is_exact=false and coverage.result_tracking=partial; it invents no new
  count for untracked results.
- **T-HOME-09 PASS at the browser cut:** ui-old-unseen is two days old, outside
  the default 24-hour recent window and within retention. It is unseen and
  remains reachable in the default Home and after Results filtering/paging
  (`116ba7`). A first probe raced the new filter response and timed out
  (`fa4269`); the corrected probe waits for the real filtered GET before
  expanding the new groups. No fake DTO or arbitrary sleep manufactures data.

final/ is the first, correlated-subquery artifact fix antecedent. final-relation/
is the authorized/grouped relation browser cut and records its actual Home SQL
hash. The final workspace-array key fence follows this browser cut and has
its own final source pin and 6-case HTTP proof; it must not be retroactively
attributed to the earlier browser. Frozen BGONN assets never changed. No final
browser/native/performance statement extends beyond those cuts.

## State and cleanup

For both browser cuts, ready.snapshot equals after-read.json for handoffs,
message_deliveries, execution_operations, execution_receipts,
execution_event_watermarks and attention_preferences. After explicit Mark seen,
only attention_preferences differs, and final-db.json matches that snapshot.
Each complete Server journal has exactly one POST: the explicit own /seen.

Both isolated browser sessions closed; all three HTTP fixture runs and their
shared WSS/lifespan/factory exited 0 (`64183b`, `e4a209`, `42cb8f`). Five exact
own Temp allocations, including failed setup attempts, were physically removed
(`5a3802`, cleanup.json); managed artifact bytes, stores and fixture keys were
not copied into the repo. No Core, protocol, Attention, receipt, ledger, Git,
proposal, package prefix or static bundle was edited by this work.
