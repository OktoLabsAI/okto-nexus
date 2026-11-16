# Separate Server lane — backend qualification

The overview and both Home attention pages partition authorized canonical
occurrences before counting/paging. Global NULL-workspace incidents have their
own Server section; project Needs you excludes them. Server contents do not
inherit project/agent/work-state selection, while the response echoes that
context and fences its own cursor with installation identity and revision.

Classic Attention retains its API and CAS. Home project paging now uses
`/home/attention`, avoiding a canonical all-workspaces page mixing global items
back into a project lane. `/home/server-attention` has its own page cursor.

The source hint is internal and workspace-only. Only explicit
WORKSPACE_BOUND=True source adapters prune; missing/False declarations remain
unscoped, as proved by a valid test-only global source family. Agent selection
is applied to the project attention list, not to receiver facts needed to
classify a logical sender->receiver handoff. A real admitted/ingested native
question, linked to a claimed logical handoff, proves that state and refs stay
intact when its sender is selected. No question or recipient is manufactured.

No global producer is installed by this change. Contract probes create valid
domain occurrence values at the canonical query port; they never violate
migrated tables' non-null workspace constraints. The absence of a producer is
not reported as a real incident execution.

The broad run was233PASS/1FAIL in234 cases. Its sole failure was an obsolete
test expecting only migrations162..166, while167 already existed. The fixture
expectation was corrected to the complete packaged list, preserving the
historical prefix, metadata-only anchor and unchanged161 checksum checks.
Two targeted corrected/renamed cases then passed. Eleven Server-lane cases
passed after the test harness exposed both canonical viewing/filtered CTEs;
one cursor case was repeated with a proper digest revision value. Counts
overlap and are never added into a fabricated single all-green broad run.

The initial unscoped read cost roughly doubled with500 unrelated project-B
handoffs. `cost-unscoped-antecedent.json` retains that finding. Workspace
pushdown removes that growth in the final measurement, but constant overhead
remains. `cost-final.json` has the exact five-sample data, one UoW/zero writes/
constant50 SQL statements, source pins and limits. This is not a production
SLO, cold-cache, HTTP/browser or native/provider performance claim.

Reproduction of the optional comparison: copy measurement-runner.py.txt to
tests/home_evolution/_measure_server_attention_tmp.py in this source checkout,
run that explicit pytest file with junit_family=legacy, then remove only that
owned temporary file. It reads baseline Home classes from Git b82a36f2 and
uses real migrated disposable SQLite. The packaged source/tests and existing
scripts/measure_home_evolution.py are required; this is not an installed-wheel
test. No raw database, trace, account data or credential is committed here.
