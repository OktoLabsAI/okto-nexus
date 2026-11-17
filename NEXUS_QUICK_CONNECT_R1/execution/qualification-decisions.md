# Bounded scenario decisions

The normative plan and its 147 scenarios are unchanged. Execution annotations
separate the scenario's literal assertion from overall qualification. A PASS
does not turn an old failed/interrupted run green, qualify a real provider, or
waive the original UI-R1 human and qualification blockers.

I08 asks whether the isolated installed package contains the entry/feature and
correct dependencies. QC11/12/13 prove that assertion for the rebuilt wheel.
Root's earlier annotation tied I08 to the broader regression gate; that was
stricter than its given/when/then and was corrected. The broad regression still
has failures, hung tests, incomplete remainders and mixed child provenance. Its
gate remains NOT_GREEN, and the draft PR is not declared ready for merge.

The independent review caught two overbroad promotions: a Git-only monorepo
does not prove C13's *Nexus-registered ancestor*, and caplog with zero records
does not prove D25's telemetry condition. Both were returned to PARTIAL
(`NOT_RUN` plus notes in the normative status vocabulary), pending separate
QC34 proofs. The later C13 registered-ancestor focal and D25 live DEBUG/file/SQL
counterpart passed; their original failures and the narrow one-byte mutex proof
remain explicit in the qualification reports. No success is inferred from the
review itself.

Completed-profile metadata may describe the current canonical association
instead of claiming another Git discovery; the exact six allowed differences
and pending-intent restrictions are documented in the Git checkpoint rationale.
F17's winner changes the canonical project proof, so a specific project-CAS
conflict legitimately precedes the namespace uniqueness check. Generic errors
are not accepted as proof of that fence.

G09 is a real hidden, isolated Windows console test, not the old tool-transport
interruption. Its signal never reached the user or RTK console. QC37 also passed
real console resizing in a separate owned-console counterpart. H09's original
argv-only evidence was insufficient for its literal per-shell-rendering clause;
the row was returned to PARTIAL pending implementation and installed proof.
WSL path tests use
an isolated temporary runtime and real Linux filesystem; they do not claim a
native Linux CI matrix, a personal installation, or a real provider campaign.

The final audit also found cancellation gaps. QC35's direct negative answer was
corrected, then the additional customization and EOF paths were reproduced red
before correction. A zero exit code or an earlier review document is not a
cancelled outcome. Source-only counterparts are separate from the final wheel.

The retained raw pytest transcript `qc09-qc-installed/shard0/stdout.txt:319`
starts its final summary with seven equals signs. Git's generic conflict-marker
check flags that literal output. It is a historical test summary, not an
unresolved merge. The immutable transcript is retained; source, test, tool,
documentation and attributes whitespace checks are assessed separately.
