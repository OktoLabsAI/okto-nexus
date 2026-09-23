# P09 — correlated native approvals, contract 1

Execution date: 2026-09-23. Parent SHA `c59a105`; migration 048 is additive;
surface revision remains 38. P09 remains IN_PROGRESS; final gate NOT PASSED.

## Implementation and traceability

`CodexAppServerConnector._on_server_request` admits only demonstrated binary
`item/commandExecution/requestApproval` and `item/fileChange/requestApproval`
requests on the current native thread/turn. Unknown methods, unsupported decision
sets, reused RPC IDs, malformed/oversized requests fail closed. Pending requests
are bounded (32 pending, 256 lifetime IDs per connection); no permission/session
amendments or automatic approval are inferred.

`EnvelopeConnector` supplies trusted provenance to the existing journal projector.
`SqliteRuntimeJournalRepo.project` atomically records the request with the event
checkpoint and its exact delivery or administrative operation. Migration 048 stores
native request identity, owner epoch, deadline, canonical approval reference and
transport outcome. Canonical agent profiles are unchanged.

`RuntimeNativeApprovalService`, wired by the production `build_dispatcher`, uses
the existing bounded publication worker and `ApprovalService`. Only the existing
authorized operator decision can accept. Current grant/policy, flags, owner,
connection and turn are checked again immediately before the native write, outside
the SQLite writer. Expiry/revocation can only downgrade to decline. Durable
SENDING precedes the write; a successful write is SENT_UNCONFIRMED, not an ACK.
Ambiguous writes become OUTCOME_UNKNOWN and are never automatically replayed.
Owner replacement fences old requests without starting a replacement peer.

`ApprovalService` adds opt-in idempotent decisions for this action; legacy actions
retain their previous semantics. Identical retries return the existing decision;
conflicting decisions fail. Native replies use bounded supervisor control helpers.

## Behavioral reproduction and validation

All commands below were prefixed with `rtk proxy`. Tests use disposable stores and
real production composition with isolated Python JSON-RPC peers unless labelled REAL.

- RED on parent: `.venv/Scripts/python.exe -m pytest -q tests/test_runtime_native_approvals.py`:
  **1 FAIL, 10.23s**, valid native request never reached canonical HITL (no import failure).
- First implementation: same targeted case **1 PASS, 5.08s**; expanded **5 PASS, 19.89s**.
- Intermediate Windows gate **44 PASS, 1 FAIL, 113.36s** and Linux gate
  **42 PASS, 1 FAIL, 1 SKIP, 74.94s** exposed missing workspace on administrative
  commands. Fixed by using the validated canonical session workspace.
- Corrected Windows approval/HITL/work-results gate **45 PASS, 99.05s**.
- `.venv/Scripts/python.exe -m pytest -q tests/test_runtime_native_approvals.py tests/test_runtime_event_journal.py tests/test_runtime_commands.py tests/test_runtime_restart.py tests/test_harness_domain.py tests/test_harness_persistence.py tests/test_harness_tools.py tests/test_harness_routes.py`:
  **115 PASS, 2 SKIP, 190.80s**. Skips are the two POSIX-only attach tool cases.
- `wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_native_approvals.py tests/test_harness_codex_connector.py tests/test_runtime_restart.py`:
  **49 PASS, 1 SKIP, 97.79s** (unconfigured legacy native provider test skipped).
  The later owner-restart case was not in that collection: Linux **NOT_RUN**;
  Windows targeted owner-restart **1 PASS, 12 deselected, 6.45s**.
- Ruff on changed production/test Python files: **PASS**.

Coverage includes accept/decline for both supported methods, caller denial,
idempotent/conflicting human decisions, post-interrupt stale approval, flag off,
grant revocation, expiry, canonical interception rollback/recovery, uncertain
write without replay, administrative turns, revocation between decision and write,
and actual owner reconstruction against the same disposable store.

## REAL Codex campaign

Installed Codex 0.156.1; temporary HOME/project/store, only explicitly selected
login copied then removed. No personal settings/hooks/MCP/sessions or Nexus key
passed to the child. Read-only sandbox and on-request approvals preserved.

Exact invocation (environment values are paths/opt-ins, never tokens):

```powershell
rtk proxy python -c 'import os,subprocess; env=os.environ.copy(); env.update(OKTO_NEXUS_NATIVE_CAMPAIGN="codex", OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe", OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.codex/auth.json", OKTO_NEXUS_PI_LIVE="0", OKTO_NEXUS_CODEX_LIVE="0", OKTO_NEXUS_CLAUDE_LIVE="0"); raise SystemExit(subprocess.call([".venv/Scripts/python.exe","-m","pytest","-q","tests/test_runtime_native_campaign.py","-k","approval_denial"],env=env))'
```

Initial stimulus incorrectly requested an action via an untrusted conversation:
**1 FAIL, 5 deselected, 11.44s**. Codex correctly refused to act without executable
authority. Corrected test creates a canonical handoff and explicit execute_work
grant. Fresh run: **1 PASS, 5 deselected, 19.31s**. Native request reached canonical
HITL, operator rejection reached the matching turn, no file was created, and the
owned process stopped through durable close. No sandbox elevation was approved.

## Limits and next dependencies

Native accept/file-change and all input/elicitation requests remain **NOT_RUN**;
binary allow/file-change are fixture-tested only. Claude native approval bridge
and native input handling are not implemented by this unit. Pi and dedicated
Claude attach native campaigns remain NOT_RUN under current operator scope.

Undecided requests expire after 300 seconds. Revocation is enforced at response;
without a decision it reaches the peer at expiry. Canonical pending approval
history is retained after native owner loss/expiry; later human decisions cannot
revive the native turn. P11 must expose/reconcile these separate states and provide
administrative surface parity. No automatic resend of unknown outcomes is allowed.
P09 remaining capability eligibility/input gates precede P10 causality, P11
administration and P12 full acceptance/build/install.
