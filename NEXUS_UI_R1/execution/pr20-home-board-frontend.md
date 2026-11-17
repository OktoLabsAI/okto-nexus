# Frontend board — frozen technical handoff

The operational Home reads one `/home/board` snapshot and renders Active,
Needs you and Results together in one Follow-up region. Columns remain present
when loading, unavailable or empty; desktop uses three columns and narrow
screens stack them. Each backend-partitioned entry is one card with its linked
sessions, questions and deliveries. Membership is never inferred in React or
assembled from legacy source first pages. Project card, compact summary cards,
local Home preference/default OFF and canonical detail URLs remain in place.

The existing HomeController serialized queue now has an additive `board`
family, sharing scope abort/generation, SSE hints, TTL polling, visual pause and
focus hold. Root/column requests omit quick. A column job captures its cursor,
global board revision and entry relation revision. 409 closes all column cursors
and related caches before a full board read. A new global revision replaces all
column pages; entry detail cursors use the separate backend `entry_revision`
with quick=all. Old-scope responses cannot revoke or populate a newer scope.
Preferences still use the existing canonical occurrence/CAS writes; their
lookup and announcements now traverse Board entries and related pages.

Read labels are explicit: View work, View session, View connection, View
delivery and Review question. Overview cards expose no Continue shortcut;
canonical contextual controls remain in the exact existing panel. No unknown
result, column assignment or visibility grants new execution authority.

**53 focused tests PASS**, 3.155 seconds (`3ad1ee`): Board API, six controller
cases, two Board rendering cases, legacy entries queue, canonical preference
lookup, exact-session targets and first-connection inventory guards. The new
controller cases exercise one root read/explicit append, separate entry-detail
revision, Active→Needs you movement without duplicate work, clearing loaded
Active/related-session pages, a column409 followed by a full resnapshot,
discarding a queued cursor on invalidation, obsolete403 after scope abort,
focus-hold/apply and duplicate cross-column rejection. They do not constitute
browser geometry, assistive-technology or provider/lifecycle qualification.

One intermediate focal run had 45 PASS / 1 FAIL (`3c8167`): an existing test
selected buttons by the obsolete “Open session” label. It was updated to
“View session”; its exact two session targets/no operation ID assertions remain.
The existing OperationalHome unit fixtures now supply Board envelopes rather
than an entries-only state; their canonical preference and inventory assertions
remain. Root subsequently reported **328/328 Node PASS plus TypeScript/Vite
PASS** on the frozen integration; that global validation is Root's run, not a
second run by this agent. Root owns the bundle and browser/installed follow-up.

No build, provider, personal authentication, Git, ledger, package prefix or paid
proposal was touched by this frontend work. The participant's earlier failed
journeys remain failed; these checks do not certify human understanding.
