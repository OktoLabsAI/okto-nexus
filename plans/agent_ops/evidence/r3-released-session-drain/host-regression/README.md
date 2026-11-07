# Normally closed session drain regression

The same single integration case fails on the historical Core wheel and passes
on the corrected Core candidate. The baseline reaches DRAINING_PENDING; the
candidate reaches DRAINED without force or safety shutdown before teardown.

The test uses installed Nexus/SQLite/Core and a synthetic native protocol peer.
It opens a session, submits a finite turn, publishes real synthetic start/terminal
events, waits for a successful canonical close and actual session eviction, then
checks a released tombstone, the exact owned slot release and positive ACKed
history. The historical claim stays pending and the opening receipt remains
SUBMITTED. Normal drain must succeed without rewriting either fact or the event
cursor. No drain-status mock, claim deletion, SQL mutation or provider is used.

Both complete XML/status/input hash records are retained. There is one unique
test case, executed once per package bundle. The corrected bundle also contains
the already qualified Windows path-normalization client; pins are explicit in
summary.json. Both runs use isolated temporary homes outside real M1 and verify
that product imports come from the installed prefix with no source shadows.

The existing lifespan cleanup runs after the assertion, including the failing
baseline. Its cleanup cannot turn the red assertion into a passing result.
This synthetic qualification does not change the pending real M1 service or
authorize force, inference, another admission or a package publication.
