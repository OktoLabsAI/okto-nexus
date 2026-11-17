# QC14 additional canonical CLI scenarios — draft only

Status: **PREPARED_NOT_EXECUTED**. Root must review/apply the external test before independently running it against the frozen installed candidate. No test/source/docs repository files were changed. No build, pytest, provider, native harness or personal installation was invoked for this preparation.

External draft: `C:/Users/jpamb/AppData/Local/Temp/nexus-qc14-extra-scenarios-8emg34b9/test_quick_connect_extra_scenarios.py`.

SHA256 `a28fa68e0c5691e1c7907b32f2905d850da66738e02c9d43a892d770a560e71d`, 6977 bytes. Python AST parsing only passed (`f6c612`); this is not collection or execution evidence. The draft has four functions / five parameterized cases.

Frozen target: source `fa031697b37a1b879d855f7858f01320addf0df7`, Nexus wheel SHA256 `a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6`, installed prefix `C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc`. QC12 is separate and was active during preparation.

The draft imports `quick_cli` and its existing canonical fixture graph from `test_quick_connect_cli`, to be placed beside that file only after Root approval. Installed execution must retain the existing isolated product-origin guard and expose only test helper directories as necessary. The peers/version checks/connection Test are explicitly synthetic and inert; the SQLite/HTTP setup, public-ID, identity, binding and grant authorities remain real.

| ID | Given / When | Required assertions |
| --- | --- | --- |
| E03 | First Codex is configured; second same-family `--new-connection` with explicit own profile and no `--id`, same workspace | Plan proposes `codex-2` without canonical mutation; approved addition binds a distinct agent/binding under that ID, preserving first profile/public row and original binding/endpoint/grant rows. |
| H06 | New project and existing-project variants; explicit-ID add with `--plan` | Exact before/after snapshot includes public IDs and project drafts as well as commits, bindings, endpoints, grants, policies, agents and workspaces; zero additional fake Test/version probe. Local review checkpoint is permitted. |
| G13 | Existing own-fixture canonical execution grants have a coherent created/expires interval wholly in the past; resume exact profile | Same configured association, not_checked session / not_submitted work, no new Test/version probe, no row mutation or grant renewal. This does not claim expired authority permits execution. |
| F17 | Two different retained review intents see the same free ID; winner approves and occupies it; loser then approves its old review hash | Loser refuses/unconfirms before any new Test/Finish/identity/grant, full selected canonical snapshot unchanged after the losing attempt, first connection/profile intact, losing checkpoint never test_submitted/finish/done. A version probe before the collision is not forbidden by this oracle. |

G13 deliberately models historical expiry using an UPDATE of only its own fixture's grant created_at/expires_at/no_expiry. It does not modify a production grant, extend authority, inject an API response or force execution. Root should retain this limitation explicitly when accepting the test. No conclusion about real provider behavior follows from any case.

If a draft fails after review/application, preserve the literal failure before adjusting anything. No assertions should be weakened merely to fit current output; any product issue must be reported to its owner. No new implementation defect was established during static preparation.
