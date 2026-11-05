# PR-03 — project introduction and shared dashboard identity

The introduction now starts with project/harness intent and reads the same
versioned preset used by terminal connect. It points to terminal work and keeps
the existing-client path available. A fresh browser checks canonical agents
before offering the introduction: the reserved operator alone is an empty
installation, while any existing project identity suppresses automatic setup.
Unknown/error responses are not treated as empty. The existing dismissed-guide
preference remains compatible across updates.

The preset GET is read-only and uses the existing operator authority on both
HTTP adapters. It exposes no credential or host path. Connections reads the
stored preset origin and current configuration. Opening the panel does not run
Finish, reapply defaults or renew a grant. Importing configuration or selecting
another harness clears the old origin indication.

Agents presents a display name separately from the canonical ID. Editing the
name and role uses the existing PATCH on that ID; other typed metadata remains
intact, including legacy non-string display metadata. No new identity store,
setup state machine or execution authority was added.

## Verification

- **40 frontend tests passed**, including four new cases for typed metadata,
  name clearing, reserved operator, existing/inactive identities and unknown
  installation state. TypeScript and Vite build passed.
- **32 source integration tests passed** for project recommendation, identity
  creation/customization, setup review, response loss and terminal reconnect.
- **76 tests passed against installed wheels**, including those source cases,
  dashboard authority, canonical setup and durable receipt recovery. These runs
  overlap; they are not 108 distinct integration cases. No skips occurred.
- Ruff E9/F passes for the changed Python modules and new integration tests.
- The Nexus wheel contains exactly the current **431 Python and seven static
  payloads**, byte-matched to source. Unchanged Connector/Core wheels match their
  **117/130** Python payloads and existing pins. See the wheel manifest.

The initial five-case source check found two missing dashboard-route registrations
(the direct /v1 route worked). Adding the existing adapter allowlist entry fixed
the actual defect before the successful suites and final wheel. The first wheel
audit also rejected obsolete JS assets retained in the repository's build/lib
directory. The tested wheel was rebuilt from a clean temporary source copy;
the exact static file set, as well as its bytes, was then checked.

## Real browser interaction

Playwright CLI drove Chromium against two disposable FastAPI/SQLite backends
served by uvicorn from the installed Nexus wheel. Existing test fixtures supplied
the canonical TerminalConnection review/Finish and synthetic native checks.
Provider execution was simulated; this is not productive M1 qualification.

1. With terminal-created project-assistant, a fresh browser did not open the
   introduction. Agents displayed Codex — Project and the canonical ID.
2. Connections displayed project-generalist revision 1, the saved binding,
   enabled runtime and per-sender context. Closing it preserved those objects.
3. Browser edits changed the display name to Project reviewer and role to Review
   specialist. The backend retained the exact ID, key hash, permissions, creation
   time, configuration, binding, grant and existing message rows. Terminal resume
   used the same receipt; probe/test counts remained one each.
4. An operator-only backend offered the project introduction with the live preset
   (60 minutes / 20 actions). Existing-client guidance was selectable. Opening
   Agents created no project agent, binding or grant. Reload after dismissal did
   not reopen the introduction.
5. Initial focus was on project intent. Shift+Tab wrapped from the first control
   to Open Agents; Tab wrapped back to theme control. Light desktop and dark
   390×844 layouts were inspected, including scrollable content and fixed footer.
6. An injected 503 on only the preset GET produced the explicit error/retry state.
   Removing the route and clicking Retry loaded the real Server recommendation.

The first state-verification attempt incorrectly required the entire message
table to stay frozen while a runtime failure notice was appended for the
synthetic executable. The repeated campaign checks every previous row unchanged
and permits independent new rows: one prior message remained intact and one
notice was added. All authority/configuration comparisons still require exact
equality. This correction changed campaign instrumentation, not product source
or the tested wheel. Both disposable backends and browser sessions were closed.

Campaign directory:
`C:\Users\jpamb\AppData\Local\Temp\r3-project-dashboard-0e24b7c5`.
prepare.py builds from a clean copy, audits all payloads and installs the three
wheels in a fresh venv. Copied tests run with python -I outside the repositories.
browser_backend.py reuses the canonical fixtures, runs the actual HTTP app and
verifies persisted state after browser interaction. Browser results and screenshot
hashes are in pr03-project-dashboard-browser.json; captures originated under
output/playwright/pr03-project-dashboard and are retained beside this evidence.

## Scope remaining

DX-12, DX-18, DX-19 and DX-21 remain in progress. DX-T49 now has installed-package
and real-browser evidence for the shared identity/configuration contract; its
productive-harness campaign remains open. Participant init/doctor, broader
capability presentation, preset evolution, new remote identity provisioning,
native login/logout/crash qualification and the full real local/remote M1 cycle
are not completed by this increment. RG-10 is satisfied for this UI campaign;
future attention UI still requires its own browser campaign. The fixed R3 plan
and its original task/scenario inventory are unchanged.

No personal installation, provider credential, native user task, package release
or merge was involved. Connector and Core source did not change.
