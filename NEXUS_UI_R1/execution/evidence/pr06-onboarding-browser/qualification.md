# UI039 — browser onboarding qualification (in progress)

This is synthetic local qualification, not a provider campaign. The application,
SQLite, HTTP authorization, inventory projection, setup-test admission/status,
Finish transaction, receipt recovery and built dashboard are real. Only the
installation/version qualification and `ConnectionTests.run` peer are substituted,
following `tests/execution_r4/test_terminal_connect.py`. No executable is launched;
provider discovery is restricted to an empty fixture-owned directory.

The runner is `tests/ui_simplification/browser_project_connect_fixture.py`. It uses
the qualified temporary Python prefix with the current checkout explicitly first
on `sys.path`, starts a real TestClient lifecycle and serves that same application
over a bounded loopback uvicorn server. Temporary homes, SQLite and generated keys
remain outside the repository. The named browser is `ui039-project-connect`.

## Antecedent and fixed preset adapter

`antecedent-ready.json` pins the previous `index-CIRJLndB.js` bundle. Resume A
opened its exact read-only connection context. Add B failed with `Invalid
authorization limits.` before any new identity/test/Finish. `canonical-project-preset.json`
records the real public shape: `minutes/actions/no_expiry/unlimited_actions`.
The frontend portable parser intentionally accepts only `minutes/actions`.

The model now checks the canonical flags and converts zero/null unlimited values
to portable nulls without relaxing the parser or hardcoding preset limits.
`node --test tests/projectConnectFlow.test.mjs`: 19 PASS (`780289`).
`npx tsc --noEmit -p tsconfig.json`: exit 0 (`bc3c38`). Root subsequently qualified
the complete 292-test Node suite and built `index-dfy1_5aT.js` (SHA256
`d4361240c4405978aefb39034e3c07e549766d338d290b313f719e282de62409`).

## Executed browser facts on dfy1_5aT

* Real API Add B did not create an agent before Finish. Test/Finish used the same
  canonical workspace as A and distinct agent, binding and workspace-binding IDs.
* On the first cut (two Codex connections), a synthetic response loss **after**
  canonical Test was recovered after browser reload by the same test-ID GET.
  Response loss after Finish, including a real double-click, was recovered after
  reload by the exact durable receipt. The journal contains one Test POST, one
  Finish POST and one receipt-recovery POST for B; no repeated synthetic turn.
  `first-cut-final.json`, `lost-test.png`, `lost-finish.png`, `finish-recovered.png`.
* The final multi-harness cut adds Claude to Codex through real canonical Test and
  Finish with an empty fixture-owned provider home. Both Resume actions open exact
  read-only contexts for the same workspace. `multi-catalog.json`, `multi-state.json`,
  `multi-ready.json`, `multi-review.png`, `multi-finish.png`, `resume-claude.png`,
  `resume-codex.png`.
* A's agent, binding, grant, endpoint and complete runtime-profile row digests are
  byte-identical before and after the Claude addition (including its model/settings).
  Counts are 4 agents, 2 bindings, 2 grants and 2 receipts. The two other agents are
  fixture operator/subject; execution sessions/operations remain zero.

## Known refusal exposed by the browser

The preliminary Claude cut deliberately had no provider-home suggestion. Test was
refused with HTTP 422, `VALIDATION_ERROR`, stage `connection.test`,
`possible_effect:false`, `retry_safe:false`, `operation_id:null`, empty action.
No peer turn, identity, binding, grant or receipt was added. The browser kept the
attempt uncertain and offered no editable review. This is a product recovery gap,
not a provider-auth failure. `claude-precondition-ready.json`,
`claude-precondition-final.json`, `claude-home-required.png` preserve this cut.
A strict, explicitly invoked edit path was applied after the installed-package
CI input freeze ended. Only the exact definitive refusal shape can enable it;
transport errors, missing/contradictory metadata, non-null operation IDs and
NOT_FOUND do not. Editing revalidates the same authenticated Server, project
access, catalogue and absent Finish, then archives the old attempt. It neither
replays the request nor starts a new test automatically.

The updated model's 22 Node focals pass (`7965cb`) and TypeScript exits 0
(`5cf1a0`). The new real-HTTP focal
`tests/ui_simplification/test_project_connect_rejection.py` passes (`19e95c`,
9.57 seconds, `http-rejection-current.xml`). That focal asserts unchanged complete
agent, runtime-profile, binding, grant, session, operation and receipt rows and
zero tests/probes/cache entries after the 422. `http-rejection.xml` is an earlier
test-authoring failure: the reused terminal review correctly rejected a missing
Claude home before the HTTP call. `http-rejection-final.xml` fixes the test setup
and passes; the current-repository run repeats that qualification.

The first browser check on `index-CwgvXyuV.js` exposed another real defect before
it could qualify rejection recovery: deferred input handlers read the controlled
DOM value after React restored its previous value. Clearing the provider-home
field and changing the name both silently reverted. A concrete read-after-Tab
check is recorded in `text-input-blocked.png`. This caused one extra **synthetic**
successful Test, with no Finish or identity/grant creation; its retained attempt
was preserved in the first tab. `text-input-antecedent-state.json` records three
peer turns but still only two connections/receipts. This is not a successful
negative-recovery result.

The component now captures primitive values synchronously before dispatching
asynchronous model actions, including the selected project object. The model's
authority remains unchanged. Node focals remain 22 PASS (`74639e`), TypeScript
exits 0 (`2c5c21`). Root then qualified all 295 Node tests (`faacd3`) and built
`index-vmhGy86G.js` (SHA256
`e4a1b963969fe42a195a904fe8238b0e5e9c927f67e97d47ba9db0eac2b926c8`).

The vmh real-browser behavioral check passes (`2461d2`): collaborator/project names, root,
cleared provider home and tool-access selection persist after Tab; the exact
review reflects those values **before** Test. One real canonical 422 refusal
then exposes explicit edit, survives reload and archives the exact rejected
request while returning to editable configuration. No additional Test/Finish or
peer turn occurs during reload/edit. `rejection-vmh-antecedent.json`,
`rejection-vmh-antecedent.png`, `rejection-edited-vmh-antecedent.png` and the executable
`browser_project_connect_rejection_checks.js` preserve the result.

That cut's final counts remain four fixture agents, two bindings, two grants, two receipts,
zero runtime sessions and zero runtime operations. The third synthetic peer turn
belongs solely to the explicitly preserved Cwgv input-reversion antecedent;
`successful-test-unfinished-antecedent.json` retains that attempt without a Finish.
All of A's configuration and identity digests still match the before-addition
snapshot. `source-pins-final.json` distinguishes available antecedent comparisons
from final-only pins; it does not invent a prior measurement for an unpinned file.

Visual inspection then found the restored selector incorrectly displayed "New
project" although the retained request still carried the correct existing
workspace ID; the host label was empty. The restored model returned before
loading its directory. This is a display/context-rehydration defect, not an
observed retarget. The edit path now reuses the complete bounded validated project
directory and reads the exact retained executor before it clears the checkpoint.
Deleted projects, absent/mismatched executors and failed option reads preserve the
uncertain attempt. Node 22 PASS (`69ff3d`), TypeScript exit 0 (`37b76a`). A separate
finite negative-only browser cut then passes on `index-CdDUCMon.js` (SHA256
`d5b986b54f8a7cad92d504707aedca7796a16ebbf80b6e9ca0a9e2e3f951a09e`,
root build `849ed0`, full 295 Node PASS `8c93d2`). `rejection-final.json` records
the actual pass (`7e640e`): restored SELECT.value equals the exact original
workspace ID, the host label matches its canonical review, and the entire
archived request/configuration is unchanged. The new cut contains only seed A:
three fixture agents, one binding/grant/receipt, zero sessions/operations and one
synthetic peer turn. The single negative Test POST adds none. Reload, explicit
edit, an unconsented new review and a second read-only tab add no POST or turn.

The first command in this new cut stopped before Connect/Test because the
asynchronous initial metrics opt-in dialog covered the button. Closing that
dialog normally allowed the sole effective negative case; this is an oracle
startup issue, not a second Test. Four final-step screenshots were inspected:
`final-choose-step1.png`, `rejection-edited.png`, `final-review-step3.png` (plus
`final-review-step3-consent.png`) and `rejection-final.png`. The disabled Test
button after the unconsented new review is recorded in
`final-reviewed-no-consent.json`. Visual inspection confirms the restored picker
shows the actual project and the host label is present.

## Scope limits

No real provider, credentials, native runtime session, Windows relogin/reboot or
remote Connector execution was used. The synthetic Test peer does not create
runtime session/operation rows; this evidence therefore does **not** qualify
opening runtime sessions from Home or the whole UI039 journey by itself. CLI,
remote-host, revoked-authority, homonymous-folder and registration-concurrency
acceptance requires its own evidence. The isolated browser is closed. The first
fixture lifecycle exited normally (`c05a7a`, exit 0), and the final restore fixture
also exited normally (`659527`, exit 0). `cleanup-first-cuts.json` confirms physical
absence of its five explicitly owned browser homes, patch directory and output;
`cleanup.json` confirms the final own home and re-created `output/ui039` are gone.
No UI039 fixture port is listening and no `nexus-ui039-browser-*` directory remains.
No personal installation was removed.
