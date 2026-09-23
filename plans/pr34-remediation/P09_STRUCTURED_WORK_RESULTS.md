# P09 — explicitly authorized structured completion

2026-09-23. Parent SHA `a9303ec`. Migration 047; surface revision 38.
This document accompanies the subsequent implementation commit. P09 and the
whole remediation remain IN_PROGRESS; native approvals and P10–P12 are unfinished.

## Authorized contract

`handoff_claim` (MCP and the corresponding REST claim body) now accepts
`completion_mode`, default `authenticated_nexus_call`. The opt-in
`structured_result_v1` permits a correlated structured native result to call the
existing canonical complete/reject service. This is the structured mapping
explicitly allowed by specification 02 §13, not a subprocess API key or a new
task engine. The authenticated admission, explicit execute_work grant, canonical
claim, current policies and endpoint/profile authorization still apply.

Admission persists this choice in `runtime_handoff_bindings.completion_mode` and
includes it in the idempotency request hash. Original manual-mode keys retain
their previous hash format across upgrade. Existing bindings default to manual;
stored output cannot retrospectively opt itself in. The admission response and
handoff runtime binding expose the chosen mode.

The bootstrap provides the exact response contract and correlation fields:

```json
{"nexus_work_result":{"schema_version":1,"operation_id":"<admitted operation>","handoff_id":"<bound handoff>","claim_epoch":1,"action":"complete","result":"explicit result/evidence"}}
```

To reject, replace `action: complete` / `result` with `action: reject` / `reason`.
One JSON object must occupy the entire captured output. No markdown extraction,
free-text classifier, guessed completion or self-verification is supported.
Duplicate JSON keys, nonfinite constants, unknown fields, wrong correlations,
boolean epochs, empty decisions and truncated captured output cannot authorize
a canonical transition. Ordinary prose leaves the claim untouched.

`HandoffService.process_runtime_results` runs in the existing bounded publication
worker before ordinary result publication, up to four captured results per scan.
The complete/reject paths independently reload and validate the exact durable
result, current serve owner, explicit mode, binding, claim epoch, grant/credential,
profile revisions and creation authority inside the same canonical write UoW.
No native or network I/O occurs there. Only these internal result paths bypass
interactive session credentials; public tool schemas do not expose their private
`_runtime_result_id` parameter.

Migration 047 adds `runtime_work_outcomes`: APPLIED, IGNORED or BLOCKED evidence,
not a work queue. A successful outcome receipt commits atomically with the actual
handoff transition, notifications and dependent updates. A commit cut rolls them
all back; recovery retries projection of captured bytes, never native execution.
Already-applied results cannot complete a later rework generation. Stale/revoked
decisions remain captured with BLOCKED evidence. `harness_get(operation_id)` and
REST operation reads expose the authorized `work_outcome` separately from native
transport acceptance and publication state.

Once applied, pending result publication becomes `WORK_APPLIED` with reason
`canonical_handoff_outcome`: the canonical transition already owns result
disclosure/verification notification. The control JSON is not sent again as a
conversational reply and successful work is not mislabeled as a publication
authorization failure. Original captured output remains available under its ACL.

Verification requirements remain authoritative: structured complete enters
VERIFYING when criteria exist, and the separate verifier decides. Native turn
termination alone is not completion. The mapping records an explicit agent
decision, not independent proof that external effects succeeded.

## Concurrency correction discovered during integration

The first expanded gate found a SQLite lock while concurrent publication tried
to insert runtime access audit rows into a read snapshot (11 PASS, 1 FAIL).
Revalidation now uses the shared authorization evaluator without adding another
audit write; admission still writes its grant/authorization audit and transport,
publication and work-outcome records preserve subsequent decisions. The focused
read-only regression asserts zero connection changes during managed revalidation.
Guardrail evaluation in this path is deterministic/read-only. Owner checks also
fence outcome recording, including ignored/blocked projections.

## Fixture evidence

Behavioral RED on parent: the same explicitly requested structured mode was
ignored; a valid native JSON decision left the handoff CLAIMED.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_work_results.py
1 failed in 10.32s (RED); first corrected case: 1 passed in 4.71s

rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_work_results.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_handoff_epochs.py tests/test_runtime_result_publication.py tests/test_runtime_grants.py
56 passed, 1 warning in 135.36s

rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_work_results.py tests/test_runtime_handoff_dispatch.py
28 passed in 88.90s

rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_work_results.py -k "revalidation or completes_canonical" tests/test_runtime_native_campaign.py
2 passed, 16 deselected in 8.53s (the -k expression deselects all native cases)

rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_handoff.py tests/test_handoff_dependencies.py tests/test_verification.py tests/test_comm_presets.py tests/test_feature_flags.py tests/test_health.py tests/test_memory.py tests/test_replay_marker.py
323 passed, 1 warning in 35.90s

rtk proxy ruff check src/okto_nexus/application/handoff.py src/okto_nexus/application/runtime_work.py src/okto_nexus/application/runtime_access.py src/okto_nexus/application/runtime_control.py src/okto_nexus/adapters/inbound/mcp/tools/handoff.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/adapters/inbound/http/routes.py tests/test_runtime_work_results.py tests/test_runtime_native_campaign.py
All checks passed
```

The read-only regression was added after the 56/28-case collections. Upstream
Starlette TestClient/httpx deprecation is the warning. Native protocol fixture
uses an actual Python child/JSON-RPC pipe through production serve/HTTP/MCP.

Subsequent expanded checks include REST/MCP contract idempotency and authorized
work-outcome reads: full `tests/test_runtime_work_results.py` **14 PASS in 49.38s**;
Linux `-k "revalidation or rest_structured or completes_canonical"` **3 PASS,
11 deselected in 15.72s**. The later `WORK_APPLIED` publication-state refinement
was checked separately (recorded below); native runs below preceded only that
publication-state refinement.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_work_results.py -k "completes_canonical or receipt_rollback or self_verify or rejection"
4 passed, 10 deselected in 14.34s
```

## Fresh authorized native campaign

Installed versions independently queried: Codex CLI 0.156.1, Claude Code 2.1.280.
Each ran `test_native_explicit_work_result_preserves_verification`: one canonical
handoff, explicit grant/mode, native structured reply, VERIFYING, separate creator
verification to COMPLETED, durable close and observed process exit.

- Codex: **1 PASS, 4 deselected, 11.09s**.
- Claude stream: **1 PASS, 4 deselected, 8.55s**.

Exact invocation for Codex (paths are configuration references, not tokens):

```text
rtk proxy python -c 'import os,subprocess; env=os.environ.copy(); env.update(OKTO_NEXUS_NATIVE_CAMPAIGN="codex", OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe", OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.codex/auth.json", OKTO_NEXUS_PI_LIVE="0", OKTO_NEXUS_CODEX_LIVE="0", OKTO_NEXUS_CLAUDE_LIVE="0"); raise SystemExit(subprocess.call([".venv/Scripts/python.exe","-m","pytest","-q","tests/test_runtime_native_campaign.py","-k","explicit_work_result and codex"],env=env))'
```

Claude used the same command with campaign `claude_code`, executable
`C:/Users/jpamb/.local/bin/claude.exe`, auth-source path
`C:/Users/jpamb/.claude/.credentials.json`, and `-k` expression
`explicit_work_result and claude_code`.

Only the specifically selected login file was copied to an isolated temporary
native configuration and unlinked by fixture finalization. Personal settings,
hooks, sessions and MCP configuration were not copied. Separate temporary Nexus
store and empty project; no operator key in child environment; no sandbox or
approval override; request forbade tools and file modifications. Model names were
not captured in this unit and are not inferred from older evidence.

Pi native and dedicated Claude attach native remain NOT_RUN. Native HITL,
steering and broader campaigns are NOT_RUN for this unit. The new native tests
skip unless that exact campaign and explicit executable/auth-source configuration
are provided. This does not certify the final gate.

Next dependencies: native approval/input bridge; external authenticated tool
bootstrap when a runtime actually needs Nexus tools (this structured completion
flow needs none); remaining P09 matrix, P10 causal relay, P11 operations, P12.
