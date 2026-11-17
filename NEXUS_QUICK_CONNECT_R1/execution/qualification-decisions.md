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
QC34 proofs. No product change or test success is inferred from that review.

Completed-profile metadata may describe the current canonical association
instead of claiming another Git discovery; the exact six allowed differences
and pending-intent restrictions are documented in the Git checkpoint rationale.
F17's winner changes the canonical project proof, so a specific project-CAS
conflict legitimately precedes the namespace uniqueness check. Generic errors
are not accepted as proof of that fence.

G09 is a real hidden, isolated Windows console test, not the old tool-transport
interruption. Its signal never reached the user or RTK console. H09 tests an
unexecuted argv array with shell=False, not a shell renderer. WSL path tests use
an isolated temporary runtime and real Linux filesystem; they do not claim a
native Linux CI matrix, a personal installation, or a real provider campaign.
