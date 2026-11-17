# Pending passive observer — no execution or new authorization

This is preparation only. Candidate SHA256:
`3ea51229df9bcc4d93d7f42dbe5e4d62a97741d97c99907a49a21cde6fafb88e`.
Campaign `062496549c9340ccb78271b640c8849a`, future own home
`C:/Users/jpamb/AppData/Local/Temp/nexus-ui042-062496549c9340ccb78271b640c8849a`,
origin `http://127.0.0.1:51076`. Do not create that directory, poll that Server,
start a browser against it, or run preparation scripts until Root explicitly
confirms the new approval and the driver's `public/observer-ready.json`.

## Canonical human authentication

The operator is independent from agent keys. `operator_auth.py` exposes
`GET /api/v1/operator-auth/status`, `POST /account`, `POST /login` and HttpOnly
cookie sessions. Loopback is initially an authenticated local operator. On this
own temporary Server only, use the actual dashboard menu → Settings → Security
→ Operator access. Confirm `configured=false` first; an existing account is an
unexpected state and must not be overwritten. Fill Username, New password and
Confirm password using a fresh random password held only in the running browser
automation closure. Use the Settings `Save changes` UI. Never print the
password, save storage state, trace the form, take a filled-form snapshot or
dump request headers/bodies.

After account configuration, use the canonical
`x-nexus-operator-session-required: 1` header to require human cookie access
instead of the local bypass, reload, and complete the real Operator sign-in
form with the same in-memory password. This is a product-supported human
session selector, not a fixture actor or an agent credential. Verify status
`authenticated=true`, `local=false`, and the exact test username. No arbitrary
auth header is accepted as authority. If the configured/login UI cannot be
completed within the finite driver window, record NOT_RUN; do not extend the
window or replay admissions.

Use an isolated Playwright CLI session `ui042-real-home-observer`, with no
personal profile, HAR, tracing, video or saved cookies. CLI password input must
be performed inside a single run-code closure (not literal CLI arguments).
Inspect a fresh snapshot before finding the account/navigation controls.

## Finite observation after Root's signal

1. Read only `public/observer-ready.json`, `codex.work.json`, `claude.work.json`
   and, if needed for IDs, the corresponding public setup/continue summaries.
   Validate campaign, origin, Server, workspace and exact session IDs. Do not
   read `private/`, provider profiles, native login material or raw logs.
2. Create the own human login as above. Select the public workspace through the
   visible dashboard selector. Open Home and click `Use operational Home` if
   needed; this only changes this isolated browser preference.
3. Generate the passive program with `prepare_real_home_observer.py` only now,
   passing `--root-execution-signal approved-and-observer-ready --output` with
   an observer-owned temporary JS path. It checks the unchanged candidate and
   reads the public files; it neither creates the campaign root nor sends HTTP.
4. Execute the generated program with the isolated CLI `run-code --filename`.
   It blocks every non-read browser request and validates canonical Home data,
   then opens each exact session through the existing `home_target` link and
   checks one drawer/one passive viewer. Missing preview refs fail closed:
   explicitly inspect canonical pagination if time permits, never choose a
   recent session or concatenate unrelated first pages as complete inventory.
5. Separately inspect visible Codex/Claude harness labels and completed result
   cards, matching public work/continue operation IDs through read-only result
   details. Record exact observed assertions and coverage; the supplied runner
   does not claim this additional visual result check automatically. Screenshots
   only after login and review that no credential field/raw secret is visible.
   Retain public IDs, bounded status/counts and sanitized paths, not native event
   payloads, cookies, headers, passwords or provider output dumps.
6. Never click Test, Finish, Continue, Mark seen, Snooze or an approval action.
   The six admissions belong only to the driver. Do not intercept/mock GET
   responses or attach fixture actor headers. Stop on authority/scope mismatch.

Only after the actual reads and sanitized evidence have been saved, write the
exact `public/observer.done` with campaign ID above and `evidence_ref` referring
to that actual evidence. This plan and generated code are not evidence and
must not trigger the marker. If coverage is partial, make it explicit in the
evidence and marker reference; never claim an unobserved result. The driver
will otherwise expire normally at 180 seconds and record NOT_RUN. Close only
this browser session; service/peer cleanup belongs to the driver.

No runtime, account, directory, marker or browser was created during preparation.
No test was executed and no campaign status was promoted by these files.
