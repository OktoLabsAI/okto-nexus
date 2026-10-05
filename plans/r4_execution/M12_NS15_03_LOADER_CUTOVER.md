# NS15.03 production loader cutover — October 1, 2026

Server tool composition no longer imports or instantiates the duplicated Pi,
Codex, Claude stream or Claude attach native connectors. Default legacy native
factories now return a migration-required conflict directing the operator to an
approved canonical runtime binding. Existing R4 callers continue to execute
through Core. Domain supervision, historical rows and explicitly injected
adapter fixtures remain available during removal of the duplicate modules.

Historical alias capabilities are inert compatibility metadata. They no longer
require constructing a native connector merely to build the registry. Live R4
catalog, availability and control contracts still come from Core.

An isolated process imports the HTTP/tool composition, reads historical metadata
and invokes every retired default factory. It verifies migration refusal and that
none of the four legacy native implementation modules entered `sys.modules`.
The installed campaign also exercises canonical caller execution, binding
migration, approved fallback and existing MCP/REST domain callers.

The old default-factory tests now assert retirement for all four substrate
choices. Native implementation files and their dependent legacy tests remain
in the checkout/package at this checkpoint; physical removal is still required
by NS15.03. This increment proves loader cutover, not complete code removal.

Canonical fallback contract review: the Server's pre-send authorization refusal
records `possible_effect=false` with `retry_safe=false`, and directs the caller
to reconcile before new work. This is not the legacy typed transport non-write
proof. Do not introduce automatic cross-binding re-selection based only on that
status. The previous legacy-to-R4 transfer remains limited to its original typed
proof and approved equivalence policy.

Evidence: `run_ns15_03_loader_cutover.py` and
`test_runs_20261001_ns15_03_loader_cutover.json`. Native peers/readiness are
fixture-qualified. Remaining duplicate-code removal, canonical-attempt policy,
full restore and final provider/platform/release gates stay open.
