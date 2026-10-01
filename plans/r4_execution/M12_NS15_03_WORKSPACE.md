# NS15.03 path-free message workspace selection — October 1, 2026

`message_create` now accepts an existing `workspace_id` instead of `project_root`.
The two selectors are mutually exclusive. The service checks the logical
workspace inside the message transaction, preserves its existing path metadata
and never resolves a filesystem path or creates an unknown logical workspace.
The existing permission, audience, channel/parent, policy and claim checks remain
in the same use case. Approval payloads retain the logical selector, so approval
re-execution does not fall back to path resolution. The MCP tool reference is
updated to version 5.

Public MCP tests use a newly created R4 logical workspace with no stored local
path, configure canonical conversation delivery, and reach Core opening/turn
execution. Path-resolution functions raise if called in that journey. Negative
tests reject missing, blank and competing workspace selectors without message
or execution writes. A real operator approval roundtrip preserves the workspace
ID. Existing conversation delivery and messages/governance/HITL regressions run
against the installed artifact. See [the manifest](test_runs_20261001_ns15_03_workspace.json).

Native peers and readiness qualification remain fixture-local. This proves
path-free logical selection on the Server; it does not qualify a remote provider.
Mixed canonical/legacy endpoint selection parity, managed handoff delivery,
context-only observation, result/event publication and native loader removal
remain pending. Normative TR4-06-05, TR4-15-03 and release gates remain open.
