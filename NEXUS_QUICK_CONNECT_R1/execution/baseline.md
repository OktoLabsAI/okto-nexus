# Quick Connect baseline

The preceding conditional harness/action Home implementation closed at
`7f114698e178c415488cd7a112d6ed0cb2ded214`, after its source, browser and isolated
package checks, cleanup, commit and push. Only then was this package inspected.
That closes the agreed implementation increment; it does not turn the separate
UI-R1 global qualification into PASS. Human availability is deferred.

All three repositories were clean before starting. `origin/main` was fetched
in each; none is behind its main. Exact refs, drift and input hashes are in
`qc00-baseline.json`. The supplied `2463c058` is an analysis snapshot, not a
checkout target. Its delta to the actual baseline is 1,081 files (mostly retained
evidence plus the Home corrections); neither was reset.

Nexus was branched from the actual baseline as `feature/v0.3.6` and bumped to
0.3.6 in Python and frontend metadata and locks before implementation. This
preserves the unmerged Home work as a stacked branch. CONTRIBUTING's normal
main-based recommendation is superseded here by the user's explicit requirement
to preserve the current implementation. Connector 0.0.13 and Core 0.0.14 stay
unchanged: public connection metadata belongs to Nexus, outside Core's strict
configuration envelope. No personal installation is modified.

Instructions inspected: the user-supplied AGENTS imports the RTK rule;
CONTRIBUTING, pyproject and current CI. No AGENTS file exists in this checkout.
CI targets Python 3.11–3.13, Windows/Linux and installed package shards. A local
source pytest result is not evidence for that whole matrix. Provider testing is
a separate gate: the prior campaign has unknown usage and blocked admissions;
Quick Connect has no new paid-campaign authorization.

The seven supplied files are frozen byte-for-byte under `input/`; Downloads is
untouched. Its validator passed 80 structural checks, with **no Nexus tests**.
The separate working ledger starts with all 147 tests NOT_RUN and 20 requirements
NOT_VERIFIED. Prior Home results remain in their original ledger.

## Source map and reuse

* CLI: `cli/main.py`, `connect.py`, `connection_picker.py`,
  `canonical_connections.py`, `connection_project.py`, `connection_reservation.py`.
  Keep ordinary profiles/checkpoints and their lock order. Add pure grammar and
  project resolution; do not introduce a second setup authority.
* Canonical directory: `application/connection_workspaces.py` already includes
  projects without bindings. Extend its pagination proof instead of deriving a
  project inventory from connection pages.
* Setup: `application/terminal_connection.py` retains reviewed requests and
  consent; `connection_setup.py` owns the outer Finish transaction and receipt.
  Public ID promotion must use that same transaction.
* Catalog/Home: `application/connection_catalog.py`, SQLite catalog/Home
  projections, and existing Home R3/context controllers. Add metadata using the
  complete canonical reference, preserving grouping and targets.
* UI: `runtimeApi.ts`, `projectConnectFlowModel.ts` and `ProjectConnectFlow.tsx`
  have explicit copy/restore allowlists that need coordinated additive changes.
  `homeTypes.ts` and existing harness cards present the same ID; no new menu.
* Tests reused: execution_r4 terminal/connect/catalog/setup/recovery suites,
  UI harness-card/controller and project-connect frontend tests. New tests live
  in `tests/quick_connect/`; real harness, browser and PTY remain distinct levels.

The main missing contracts at baseline are public ID uniqueness, its atomic
reservation/receipt, project directory revision, safe Git hints, pure short-form
parsing, and an output invariant that distinguishes configured from work/session
readiness. Existing flags already reject unknown service options during later
configuration resolution; this work moves grammar validation ahead of reads.
