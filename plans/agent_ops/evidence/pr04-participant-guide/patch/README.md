# Proposed participant dashboard guidance patch

Prepared outside the checkout. NOT APPLIED TO THE CHECKOUT. The complete frontend
from base e607d012 was copied into a new Temp directory and overlaid with this
candidate. Focused tests, the full frontend suite and build/typecheck passed there.
No browser, HTTP, vault, native service or provider campaign has been executed.
These are frontend code/render checks, not qualification of a real MCP client.

Repository: `D:/Projetos/Techridy/okto_labs_okto_nexus`.
Base: the files read after Nexus milestone `e607d012` (full head and file hashes
are retained in `manifest.json`). Reconcile against later changes before applying.

## Scope and requirements

- DX-04 / DX-T09: remove generated secret-bearing commands/configuration, keeping
  the dedicated one-shot key delivery and manual protected transfer unchanged.
- DX-04 / DX-T11: preserve the selected HTTPS origin/port, reject credentials,
  path/query/fragment and remote HTTP, with a contextual note for loopback.
- DX-05 / DX-12: existing identities and onboarding reach the same public guide
  without creation/rotation, runtime changes or host file effects in the browser.
- Preserve DX-T01/T03/T10/T35: existing identity/runtime, explicit local CLI
  review/apply, actual process environment caveat and independent proof levels.

The patch removes the internal `mcpSnippet` UI helper and its secret-bearing
consumer buttons. No HTTP/API/authentication/legacy MCP protocol is changed.
The dedicated one-shot key display/copy remains unchanged. This is not a new key
issuance, rotation, remote approval, preset or runtime feature and does not claim M2.

The helper accepts only public setup fields. It uses the CLI already shipped:
`init --mode participant`, `participant launch`, and `doctor --mode participant`.
It generates review commands and explicit revision placeholders, never executes
them and never supplies a key. Guide state is local to the mounted component.
The profile and IDs are not automatically inferred from names or project paths.

## Candidate files

1. `frontend/src/participantGuide.ts` — pure origin/argument validation and public commands.
2. `frontend/src/components/ParticipantGuide.tsx` — local-only public guide,
   supported/manual-client distinction, copy feedback and proof caveats.
3. `frontend/src/views/AgentsView.tsx` — an existing-client action independent of
   key issuance; secret-bearing snippet buttons removed, one-shot panel retained.
4. `frontend/src/components/onboarding/OnboardingModal.tsx` — same guide for existing clients.
5. `frontend/src/api.ts` — remove only the internal snippet generator; API calls unchanged.
6. `frontend/tests/mcpSnippet.test.mjs` — seven public-command contract tests replacing four old snippet tests.
7. `frontend/tests/participantGuide.test.mjs` — five React static-render tests.
8. `docs/terminal-participant.md` — minimal dashboard entry/limitations documentation.

## Isolated validation completed

Directory: `C:/Users/jpamb/AppData/Local/Temp/dx04-participant-guide-validation-2uf9880h`.
The existing dependency directories are referenced through individual junctions;
the node_modules root is physically in Temp, so Vite's temporary config/cache
directory is also in Temp. No dependency installation or package change occurred.

- `focused-initial.log` / `.json`: 16/16 passed (12 new/updated guide cases plus
  four project-identity regressions).
- `suite-initial.log` / `.json`: 138/138 passed; `build-initial.log` / `.json`:
  `tsc -b && vite build` passed. The initial static output is retained in
  `build-initial-static/`.
- Code review then aligned HTTP origins with the existing CLI normalizer's exact
  localhost/127.0.0.1/::1 set, refused port zero and control characters. Added
  negative inputs to the existing origin test (no backend change).
- `suite-final.log` / `.json`: the stricter origin version passed 138/138, zero
  failures/skips; `build-final.log` / `.json`: typecheck and build passed.
- UX review removed the origin/locality checkboxes and generation gates, and
  reduced repeated guidance. Public commands now appear as soon as the fields
  are valid. Approval remains in CLI review/apply. `suite-ux-final.log` / `.json`
  passed 138/138; `build-ux-final.log` / `.json` passed typecheck/build. Vite emitted
  its bundle-size advisory. These UX-final reports qualify the current candidate.
- Final static: `src/okto_nexus/adapters/inbound/http/static/` inside that Temp
  directory, never the checkout. Hashes and source-to-candidate correspondence
  are recorded in `validation.json` beside this README.

Basic accessibility review: native labelled inputs/selects; named
section/headings; per-step copy button labels; status feedback; readonly selected
identity; existing modal's focus/Escape mechanism; no forced approval from typing.
Origin edits clear pending copy feedback. Public commands appear immediately
when the required public fields are valid; there is no approval gate or checklist
in the guide. Concrete effects remain subject to CLI review/apply. Public shell
values are quoted for the selected PowerShell/POSIX shell;
controls and credential-shaped IDs/profile names are rejected. These reviews and
SSR checks do not substitute for keyboard/mobile/browser interaction testing.

The unvalidated proposal is retained as `participant-guide-unvalidated.patch`,
`manifest-unvalidated.json` and `README-unvalidated.md`. The first validated
version before UX simplification is retained with the `-validated-gates` suffix.
No test/build failures occurred; the origin limits and UX changes came from code
review and were then revalidated.

## Validation remaining after review/apply and source freeze

1. Verify patch applicability and final source/installed asset hashes on the new
   milestone. The isolated frontend tests/typecheck/build above already pass;
   rerun if integration changes the candidate. No new dependency is needed.
2. Real installed dashboard + synthetic identities/workspaces: reach the guide
   from existing agent and first-install introduction; no create/rotate/mutation
   request from opening, editing or copying guidance. Keep real key delivery out
   of browser captures; use public guidance only in artifacts.
3. HTTPS/default port/custom port/IPv6, contextual loopback guidance,
   changed-origin validation, escaping/PowerShell and POSIX commands,
   clipboard permission failure and pending clipboard feedback after edits.
4. Keyboard focus/Escape, viewport/mobile scroll, theme, close/reopen, existing
   managed connection preserved. Generic selection must not offer launch or
   claim client qualification. New guide must remain reachable with no fresh key.
5. If later qualifying the commands themselves, use only a new temporary home,
   synthetic identity and explicitly bounded fixtures. Existing init/launch/doctor
   regressions already test the implementation; this patch adds no production host
   effects. Do not turn a synthetic browser check into a claim of real client readiness.

## DX-02 evidence nuance: leave broad `actual_client_credential_resolution` NOT_RUN

Earlier review called this entry stale too broadly. There is good evidence of
actual native clients resolving an environment reference and authenticating MCP,
but not the complete real OS vault → shipped participant launcher → real client chain.
Do not promote the broad subscope or change the ledger with this patch.

Exact repository-relative sources (all under the repository above):

- `plans/agent_ops/evidence/pr04-participant-launch-native.json`: four recorded
  cases, Claude Code 2.1.317 and Codex 0.166.0, environment reference present and
  absent. Present cases have authenticated initialize; absent cases do not,
  although all four exit zero. Explicit limitation: no real Server identity or
  OS vault in native-client qualification; synthetic responder and random fixture
  credential; protocol modes, no model turn/tools call.
- `plans/agent_ops/campaigns/participant-environment.py`: lines 82–85 construct
  and apply the Core fixture configuration; line 86 directly calls
  `child_environment(contract, KEY, env)`, lines 87–88 remove the reference for
  negative cases; lines 89–90 use installed launch-context helpers; line 106
  starts the real selected binary with that environment. The fixture does not
  invoke real vault acquisition or the whole CLI launch flow. This is explicit
  programmatic fixture injection, not an observed interactive user export.
- `plans/agent_ops/evidence/pr04-participant-launch.md`: Validation and
  Corrections and limits explain the distinction and explicitly leave the
  complete real-vault/interactive-client/cooperation chain open.
- `plans/agent_ops/evidence/pr04-participant-launch-source.xml`: 19 prior passes;
  `pr04-participant-launch-installed.xml`: 74 prior passes. Includes
  `test_real_subprocess_receives_reference_without_parent_mutation` and scoped
  environment/replay tests. These application tests use a synthetic vault;
  a real subprocess is not by itself a real MCP client/vault end-to-end proof.
- `plans/agent_ops/evidence/pr04-participant-removal-vault-source.xml`: one prior
  passing `test_windows_participant_vault_compensation_and_absent_replay` case.
  This separately exercises fixture storage/removal in Windows Credential
  Manager. It does not join that vault to the actual Claude/Codex launch campaign.

The narrower result may be described as "native client environment-reference
resolution and authenticated MCP initialize, with negative cases, on the declared
Windows builds". GUI/TUI inheritance, full vault-to-client integration, canonical
cooperation and productive M1/M2 remain unqualified by these reports. No ledger,
report, campaign result or acceptance criterion is edited here.
