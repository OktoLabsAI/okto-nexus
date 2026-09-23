# Native protocol evidence for pending P09 integration

Observed above `e054720`, 2026-09-23. This is a local binary/schema inspection,
not a model execution or a completed approval bridge. Evidence:
`evidence/p09-native-protocol-survey.json` (versions, schema hashes and fields).

Codex CLI 0.156.1 generated its own JSON schemas using
`codex app-server generate-json-schema --out <temporary-directory>`. The
schema advertises `thread/start` developerInstructions/baseInstructions/config
and separate approvalPolicy/sandbox fields. This proves the local schema, not
successful Nexus bootstrap or authorization. No configuration was applied.

Native approval requests include threadId, turnId and itemId; command approvals
may also have a distinct approvalId for several callbacks under one item.
The JSON-RPC request ID must remain separately correlated. Command/file
responses require `decision`; one-shot accept/decline/cancel differ from
session-wide approvals and policy amendments. These broader grants must not
be inferred from an ordinary one-shot Nexus decision. Current connector
`_CodexTransport._dispatch` still replies method-not-found to server requests;
P09 native HITL is therefore NOT IMPLEMENTED, despite the peer's schema.

Claude Code 2.1.280 `--help` advertises stream-json input/output, mcp-config,
strict-mcp-config, append-system-prompt and permission-mode. Help alone does
not demonstrate incoming approval frames or a safe reply contract. The current
stream adapter handles interrupt control_response but has no approval bridge.
Do not infer an implemented approval capability from these flags.

No provider/model was called, credentials copied, session attached, sandbox
relaxed or operator key injected for this inspection. Pi native and dedicated
Claude attach remain NOT_RUN per the recorded authorization boundary.
