# P03/P08 — connection-scoped backend secret redaction

2026-09-24. Parent3532111 on feature/v0.2.0; implementation originally developed
in a detached e388227 worktree while main's full regression was frozen. Only the
four reviewed source/test paths were integrated after that full run completed.
Schema061, surface56 and identity24 are unchanged. Final gate NOT PASSED.

## Reproduction

T-AUTH-09/F13 was not covered by the green e388227 full suite. The separate audit
resolved a synthetic opaque credential from an approved profile, supplied it to
an owned Python protocol peer, and observed that the echoed value survived in
journal bytes, durable output and replay. The existing journal scrubber matched
credential-shaped strings/keys, not arbitrary known backend values.

`tests/test_runtime_secret_redaction.py` initially reproduced four behavioral
failures: one complete output frame, two split frames, one-character fragments,
and a native handshake exception. The constructor exception path was already
safe. RED:4 FAIL/1 PASS18.38s; no missing-import or proposed-module failures.

## Implemented boundary

- `BackendSecretRedactor` receives only already-resolved approved profile values,
  and credential-named environment values when ambient inheritance was explicitly
  enabled. No additional credential files, personal homes, network or secret
  resolvers are read. No secret values or hashes are stored in a global registry.
- Construction and configuration errors are sanitized before crossing the
  facade. `QualifiedConnector` sanitizes startup metadata/compatibility reports,
  command/lifecycle exceptions, normalized events and native approval content.
  Existing per-session event selection and native parsing/correlation remain in
  the adapter. Both REST/MCP and boot/on-demand construction use this composition.
- Literal values and their JSON/repr escaping are masked. Known credential values
  split across output frames are handled by a bounded per-attempt stream buffer.
  The longest possible unresolved suffix is held until subsequent text or the
  correlated terminal, whose captured record contains the final safe suffix.
  Snapshots replace earlier text correctly; two turns do not share output state.
- Native raw text-bearing payload fields are explicitly withheld for these
  credential-bearing connections, so joining raw deltas cannot reconstruct a
  value removed from normalized output. Protocol metadata and authoritative
  operation/attempt/epoch fields remain. Safe text is retained in output_text.
  `_nexus_redaction.version=2` and the server-owned compatibility report identify
  this policy. The existing journal frame format/version is unchanged.
- Approval request IDs/hashes remain correlated with the native in-memory
  original. Only the existing authorized operator decision can send a reply;
  redaction is not approval. A Claude accept still uses the original in-memory
  input, while private result/approval projections expose the redacted content.
- `RuntimeCommandNotSent` and `RuntimeLaneBusyBeforeWrite` retain their exact
  types. Other failures remain uncertain errors and do not gain safe-retry proof.
  The existing sandbox, native approval and owner/process cleanup are unchanged.

The scope has at most128 distinct values,16384 characters per value and65536
characters in total before bounded escaping. A stream iterator holds at most64
pending correlation contexts, with each tail bounded by twice the longest
escaped value length. Exceeding these limits fails explicitly; no unbounded
thread, retry or buffer is introduced. All resolution/compilation happens outside
SQLite writers. No new migration or second work queue was introduced.

## Evidence

Detached worktree command (original five cases):

```text
rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_secret_redaction.py
```

After implementation:5 PASS18.31s. Expanded development run:8 PASS/2 FAIL15.31s;
the two failures were a misplaced test assertion referencing undefined fixture
locals, not behavior regressions. The assertion was restored to its production
fixture test before integration. This intermediate failure is retained here.

Main Windows broad selection:

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_secret_redaction.py tests/test_runtime_native_approvals.py tests/test_runtime_native_inputs.py tests/test_runtime_claude_approvals.py tests/test_runtime_safe_retry.py tests/test_runtime_endpoint_fallback.py tests/test_runtime_effective_capabilities.py tests/test_runtime_production_multiplex.py tests/test_runtime_capture_projection_isolation.py
```

107 PASS327.01s. After adding actual Codex/Claude approval accept/deny cases with
the known secret and the bounded-stream assertion:

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_secret_redaction.py
```

15 PASS33.35s. These counts overlap and must not be summed. The approval cases use
owned Python protocol peers, actual production HTTP/MCP/journal/HITL and exact
native reply IDs. They do not execute a provider or a requested native tool.

The same expanded broad selection completed on Linux as exec16987:
112 PASS428.29s, using:

```text
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_secret_redaction.py tests/test_runtime_native_approvals.py tests/test_runtime_native_inputs.py tests/test_runtime_claude_approvals.py tests/test_runtime_safe_retry.py tests/test_runtime_endpoint_fallback.py tests/test_runtime_effective_capabilities.py tests/test_runtime_production_multiplex.py tests/test_runtime_capture_projection_isolation.py
```

Ruff PASS for the three implementation files and the new test module.
Installed versions read without model calls: Codex0.156.1, Claude2.1.281.
Fresh real-model frame campaigns remain NOT_RUN for this unit until executed.

An existing production overflow test exposed a regression in the first redaction wrapper: process cleanup and uncertainty survived, but NativeEventOverflow became a generic error. RED:1 FAIL/15 deselected21.95s. The wrapper now preserves trusted local bounded-buffer, replay and framing fault types. Broader Windows selection59530:146 PASS362.40s.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_secret_redaction.py tests/test_runtime_event_buffers.py tests/test_runtime_protocol_limits.py tests/test_runtime_work_results.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_result_publication.py tests/test_runtime_boot.py tests/test_runtime_endpoints.py tests/test_pr34_remediation.py tests/test_import_boundary.py
```

The final namespace test reproduced1 FAIL/16 deselected1.02s. Native _nexus_redaction and compatibility backend_secret_redaction labels are removed before server policy is attached.

The final outcome of handle78014 could not be recovered across continuation and is not counted. Fresh final selection24004 completed on Windows:56 PASS121.13s;60494 completed on Linux:56 PASS125.26s. Exact commands and final source hashes are in evidence/p03-backend-secret-correction.json. Evidence tooling:16 PASS0.21s; Ruff PASS.

## Limits and next dependency

This is known-credential redaction, not a universal detector of arbitrary secrets,
encoded exfiltration or values hidden in opaque external credential files. It
does not authorize reading such files. Retained raw payload text is intentionally
less detailed for a credential-bearing connection. Text still held before a
terminal is transient; a crash before capture does not fabricate a durable
result or native replay. Existing owner recovery reports uncertainty.

Correction committed/pushed as752cd72 on feature/v0.2.0. Execute the
approved installed Codex/Claude frame campaigns at that SHA, and continue the
remaining original matrix and P12 operational/performance gates. Pi/dedicated
attach native remain NOT_RUN; installed Nexus0.1.10 still awaits final0.2.0 build.
