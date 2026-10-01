# NS15.03 canonical managed handoff delivery — October 1, 2026

The existing managed `handoff_claim` path can now select an approved canonical
managed endpoint. Its claim, execution-work grant consumption, causal message,
exclusive inbox reservation, handoff binding and R4 opening/turn admission share
one transaction. Repeating the original claim key retains the same logical
operation and does not consume another work execution. The recipient's normal
canonical execution grant is still required in addition to the work grant.

Dispatch and initial opening lease authorization revalidate the current handoff
owner/epoch, actor credential, work grant, creator/claim policy and endpoint/profile
revisions. Governed work uses the handoff validator rather than ordinary
conversation-send policy. The full handoff envelope, including claim epoch and
completion instructions, enters Core as context. The legacy dispatcher excludes
the mapped operation. `handoff_get` exposes bounded canonical operation/session
references only through its existing authorized runtime-execution view.

An authenticated terminal receipt does not complete, reject or verify a handoff.
The claimant must use the existing governed completion call. Canonical
`structured_result_v1` is refused until canonical result publication is integrated;
the existing legacy completion contract is preserved. Capacity counting recognizes
canonical terminal receipts without changing the protected handoff claim lifetime.

Public MCP tests cover stable claim replay, one opening/turn, one work-grant debit,
canonical history references, native terminal without handoff completion, explicit
governed completion, grant/claim-epoch changes before dispatch, and atomic rollback
of claim and work budget when canonical execution is unavailable. Installed
campaigns include native action authority and affected legacy handoff/result/grant
regressions. See [the manifest](test_runs_20261001_ns15_03_handoff.json).

Native peers and readiness qualification remain fixture-local. The tested
handoff surface uses an existing path-based logical workspace; path-free handoff
authoring/claim and combined MCP/local/remote claim competition still need acceptance.
Canonical structured results, result/event publication, context-only observation,
cross-protocol fallback and native loader removal remain pending. Normative
TR4-06-05/TR4-15-03 and release gates remain open.
