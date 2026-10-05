# NS15.03 logical handoff workspace — October 1, 2026

All eight public MCP handoff operations accept an existing `workspace_id` as
an alternative to `project_root`. Logical selection does not resolve a path on
the Server. The service rejects competing or invalid selectors, verifies
workspace existence inside the domain transaction, and retains actor, visibility,
claim, work-grant and approval authority. Managed session capabilities remain
bound to their approved workspace. Approval replay persists the logical selector.

HTTP claim and verification, Meta-harness authoring and operator steering use
their existing logical workspace identifiers directly, including workspaces whose
`root_realpath` is null. The original domain services still own authorization.

The public regression creates a handoff through MCP, claims through HTTP, replays
through MCP and completes through the governed tool after Core delivery. It
asserts one opening/turn and no Server path resolution. Negative selectors leave
no handoff or execution writes; approval replay retains the logical workspace.

Installed campaign evidence is produced by `run_ns15_03_handoff_workspace.py`.
The HTTP and fixture-recheck runners supplement it against the same installed
wheel: **334 distinct product tests and 3 architecture checks passed**. The
initial legacy log retains three failures caused by obsolete test composition
and a stale surface-revision assertion; the affected suites passed after fixture
correction. Repeated passes are counted once in the final manifest.
Native peers and readiness qualification are fixture-local. Combined
MCP/local/remote claim competition, canonical structured results, result/event
publication, context-only observation, cross-protocol fallback, native loader
removal and final restore/release acceptance remain pending. This increment does
not close normative TR4-06-05/TR4-15-03 or release gates.
