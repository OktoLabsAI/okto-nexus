# PR-03 — Connector project recommendation and one review

Connector connect now proposes a sole full host installation without a selection question or executable probe; material ambiguity asks once and Pi keeps its Node/script installation identity. Saved discovery roots and observations are preserved, explicit filters must match inventory, and a changed inventory refuses the review. The existing configure/checkpoint flow supplies current project, label, provider directory and preset defaults; advanced preferences are optional through --customize. Full paths, settings, limits and effects are shown before Finish. Decline performs no registration/probe/daemon effect; canonical operator approval remains separate from participant consent. 90 source tests passed, then 2 full-entry cases passed. The installed packages passed 201 Connector tests plus 2 additional full-entry cases and 22 Nexus integration tests. No production source changed between installed runs. Initial remote identity provisioning, real-provider M1 and the full R3 plan remain incomplete.

Previously connect projected inventory to paths, reconstructed candidates (losing
the discovered Pi pair), always asked for installation selection, and ran a
version probe before the user saw the setup review. It then required the full
advanced preference questionnaire. The entry now preserves Core candidates from
the same configured host discovery used by daemon publication. A sole match is
recommended; multiple matches require a concrete installation choice. An adapter
hint filters candidates without also requiring an executable path. Explicit
executable/Node filters do not silently select another target or invent inventory.

Discovery stays passive. Version/protocol checks use the existing acknowledged
probe checkpoint after Finish. Inventory revision is checked again before review.
The default project path is the current directory. Workspace choices remain
explicit when necessary; a path/name never establishes Server access. Provider
directory discovery and native harness defaults are shown for consent, not treated
as proof of login/readiness. Custom settings use the same configuration and Finish;
no separate storage, authority, grant mechanism or preset version was introduced.
An already reviewed request rejects --customize rather than resetting its choices.

The review now prints full paths and settings without table truncation. It states
the selected executable (and Pi script), folder, Server/agent/workspace, provider
directory, model/overrides, conversation policy, tool approval, execution limits
and subsequent host effects. Startup retains its existing optional choice. The
human operator still decides the canonical proposal from their own client; local
confirmation never substitutes for that authorization. No project task is sent.

## Validation

- **90 source tests passed**, covering selection, ambiguity, exact Pi pairs,
  inventory changes, cancellation, optional settings, pending recovery, saved
  identity reuse, startup and the existing exact-second-installation regression.
- The initial source run had 82 passes and 8 failures. Seven were synthetic
  candidate hashes outside the actual Core schema; those fixture hashes were
  corrected. The remaining case exposed truncated provider paths in the review;
  production rendering was corrected before the successful source run and build.
- **201 installed Connector tests passed**, including identity/vault, HTTP,
  onboarding, current-consent reconnect and a disposable detached lifecycle.
- **2 additional installed full-entry tests passed** for Codex and Pi after
  adding them to the final test file. They invoke run_connect and the real wizard
  together with injected inventory/peer/vault effects. One final confirmation is
  reached, the current folder/defaults and exact installation are visible, and
  decline produces no host effects or setup state. The package is identical to
  the 201-test run; these two cases were not included in that earlier report.
- **22 installed Nexus integration tests passed**, exercising real HTTP handlers,
  authentication, SQLite, operator review, background apply, receipt recovery and
  subsequent revocation. Native provider execution and vaults remain simulated.
- Installed CLI help exposes --customize; empty-state connect refuses without
  credential entry. Isolated python -I imports resolve within the test environment.
- The **431/117/130** Python payloads of Nexus/Connector/Core match source bytes.
  The tested Connector artifact is pinned in vendor/ci with its verified hash.
- Ruff E9/F passes for changed production modules and new/modified unit tests;
  E9 passes for the legacy audit file. Its full F check still reports 12 existing
  unused-variable/fixture-import findings outside the changed test. Whitespace,
  manifest and fixed-plan ledger checks are performed before commit.

Campaign: `C:\Users\jpamb\AppData\Local\Temp\r3-connector-review-73a4ab67`. prepare.py builds the Connector, byte-audits unchanged
Nexus/Core artifacts and installs all three wheels plus test dependencies in a
fresh venv. validate.py connector/nexus runs copied tests outside the repositories.
The extra command selects test_connect_entry_reaches_one_review_with_current_folder_and_complete_installation
from tests/unit/test_connect_project_review.py with that venv's python -I -m pytest.
Reports remain separate; source and installed runs overlap.

Connector commit: `b31677071d6531d9472e18d168d631a294f28c36`.
Connector SHA-256: `63d99d1644555cb9be2b56ed4b31a0f0f5aabf50128078c33dc3e116c601d919`.
Versions and branches remain 0.3.3 / 0.0.12 / 0.0.14. Nexus production and Core did
not change. No real user credential was accessed, personal service installed,
provider inference performed, package released or branch merged.

## Remaining scope

New remote identity creation is still missing. Current executor registration
requires an existing canonical agent key; the key issuer returns plaintext once.
There is no current pairing/enrollment transport between the participant and
operator terminals. A preference question was sent about reviewed pairing versus
explicit operator pre-provisioning; no answer had arrived when this increment was
recorded. This does not introduce a new authority or claim the new-user path is
complete. The fixed plan remains unchanged. M1 real local/remote provider work,
native campaign, participant clients, preset evolution, dashboard, ATN and OBS
remain open. Native campaign authorization remains pending.
