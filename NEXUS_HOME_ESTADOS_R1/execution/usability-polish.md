# Home usability polish

The participant found work via the Home card and identified distractions in
the inspection panel. The updated panel shows the read-only terminal and
exact actions without printing session, executor or project identifiers as
body text. An eligible session has a disclosure with its exact Nexus CLI
command and a copy button. The command opens the interactive work prompt for
the given session through the existing saved connection. A future task can
validate the copied command in the participant's terminal.

The card identifies named work by its approved title or subject. The read
query recognizes the text subject explicitly saved by the operator's
structured Ask for work request. It prefers the canonical task title,
limits extraction to a bounded payload and passes only the label through
the existing Home redaction. Direct turns with private prompts use their
state and inspection action. The card shows local receipt time with the
original timestamp in the HTML time element. The reconnect limitation is
available in the explicit connection view.

The 407 frontend tests and TypeScript/Vite build passed. The 21 tests in
`tests/home_evolution/test_home_queries.py` passed on the final source,
including scoped queries, unchanged table counts, an explicit handoff
subject, and invalid or unstructured subject fallback. The initial targeted
test addressed an out-of-scope fixture ID. The corrected test validates the
union in All projects and the title and authority in a project scope.
Ruff reported the same 20 diagnostics on the changed Python files before
and after this change.

The broader checkout regression collected the first test version. It
finished with 356 passes and one failure, the same out-of-scope lookup
documented above. The final 21-test query run passed with the corrected
fixture. The broader run retains its original result.

The [first Chrome run](ui-cleanup-overlay-browser/cut-1/qualification.json)
reproduced a remaining generic label on a delivery preview. The
[second run](ui-cleanup-overlay-browser/cut-2/qualification.json)
passed 13 focused checks with the corrected frontend
bundle and the installed R9 API. It verified the exact target, local date,
hidden basic identifiers, terminal command and copy control. Clipboard
contents were kept outside the browser exercise. The SQL change was
exercised by the separate source SQLite tests.

The offline build and Twine validation passed for the wheel and sdist. The
new SQL source, HTML and JavaScript in the wheel match the tested checkout.
The wheel hash is
`bec841b04c753b5ebc93369b05877b78cdc7e7d53f88ac09d59dad911ef6b09d`.
The sdist hash is
`67a4247f4ab06554230b25a866d1691ebe08920fb4b8842b77a56b06bc12be44`.
There is no schema change. The existing classic Home selector remains the
presentation rollback. The fresh package and these checks do not close
the outstanding full installed regression or participant acceptance gates.
