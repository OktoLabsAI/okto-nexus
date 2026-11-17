# HST-00 baseline

The inspected baseline and actual initial Nexus HEAD are both
`f28a31a22436c366a4c8dbdf5e3b250d606a61be` (0.3.6). All three repositories were
clean; fetched main is already an ancestor in each. Exact refs, drift, immutable
package hashes, dependency pins and instructions are in `baseline.json`.

Nexus now uses `feature/v0.3.7`, version 0.3.7 in Python/frontend/locks. The new
branch preserves the unmerged Home/Quick Connect work; returning to main would
discard that intended base. Core/Connector are read-only references unless an
actual unrepresentable proof gap requires a separately documented change.

Source inspection: `App.tsx` retains the explicit local-storage operational-Home
opt-in (`okto-nexus-home-operational === enabled`) and server feature gate. No
default change, release, deploy or personal-install mutation is authorized.

HST-00 work ownership: Root owns Git, ledger, version, API negotiation and the
shared contract. Native audit owns source/blocking matrix; Results audit owns
verification provenance; frontend audit owns paused-identical-poll reproduction.
All three audits begin read-only. Implementation starts after their contract
reconciliation, preserving the current controllers and read-only terminal.

Validation: input `verify_package.py` PASS (32 tasks/116 scenarios/20 requirements/
7 stages; document integrity only). `uv lock --check` PASS (106 packages).
Actual commands follow CONTRIBUTING and the current installed CI: frontend
`npm test` and `npm run build`; focused Python Home suites, then an isolated
built-wheel installed campaign; Twine/pip checks. New persistence/event changes
also require the existing live HTTP/MCP smoke. No paid campaign is authorized.

The final human evaluation is deliberately last: candidate implemented, automated
domain/HTTP/Node/browser checks and package ready, then a neutral task script and
the exact tested browser candidate. No participant is requested during development.
Prior human failures, UNKNOWN campaign accounting and broad NOT_GREEN gates are
retained and are not reused as this plan's positive evidence.
