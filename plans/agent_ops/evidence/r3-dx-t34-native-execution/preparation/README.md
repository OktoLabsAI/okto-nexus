# DX-T34 isolated missing-login preparation

This is a finite preparation, not an executed native campaign or M1 acceptance.
No native process, service, login, provider inference, personal configuration or
credential was used while preparing it. Tests use in-memory peers and disposable
SQLite fixtures only. Installation and the real case remain for root review.

The user already authorized continued implementation and testing. The required
proposal SHA binds an invocation to the reviewed preparation; it does not request
another human authorization of a hash. Do not run this case concurrently with the
paid M1 campaign unless root explicitly selects that scheduling.

## Finite execution

`run_case.py install --reviewed-proposal-sha FINAL_SHA` prepares one own venv from
the previously pinned dependency manifest, then installs only Nexus 0.3.3 wheel
`f8bd4291…` and Core 0.0.14 wheel `a05e4255…`. It neither starts the service nor runs
Codex. It must run with the Windows C:/Python313 base interpreter. Product payloads
are checked byte-for-byte against both pinned wheels before runtime imports.

Then use that own venv's `Scripts/python.exe -I -B run_case.py run
--reviewed-proposal-sha FINAL_SHA`. The campaign directory must not exist. Its
creation consumes the execution attempt, including a failed one; no automatic
new attempt or setup replay is available.

1. Create only the new own project, Nexus home and provider home. Protect that
   tree for the current Windows SID and SYSTEM. Environment uses own HOME,
   USERPROFILE, CODEX_HOME, APPDATA, LOCALAPPDATA and temporary directories. It
   inherits no API keys, proxies or personal provider paths.
2. With the exact qualified Codex 0.157.0 fingerprint, send only `initialize`,
   `initialized`, `config/read` and `account/read(refreshToken=false)`. The
   effective configuration must report `cli_auth_credentials_store=file` and
   the default OpenAI provider. The account response must explicitly contain
   `account=null` and `requiresOpenaiAuth=true`. Any other outcome refuses the
   service/setup stage. Close stdin normally and observe that exact child exit.
   No thread, turn, login or refresh RPC is sent by this preflight.
   Each native RPC and normal EOF exit observation has a 30-second bound.
3. Start one disposable detached Nexus service on its own loopback port. Capture
   its PID, birth and generation with a retained Windows process handle; confirm
   readiness and the same canonical identity again after handle capture.
   Canonical service startup gets 120 seconds; its CLI wrapper gets 150 seconds.
4. Run the actual installed connect parser: plan one fresh profile/agent and
   review the exact selected candidate, own provider/project paths, empty secret
   bindings/settings, no auto-claim and bounded standard authorization. Apply
   exactly that review once. The CLI observation limit is **120 seconds per
   existing phase** (installation check and test); the wrapper allows **270
   seconds overall**. These are not M1's model-turn deadlines. No M1 token ledger
   or reservation is created or reset.
5. Expect `test_failed`, `PROVIDER_AUTH_REQUIRED`, `work_state=not_submitted`,
   completed cleanup (`retryable_failure=true` in the canonical public response),
   and concrete `codex login` guidance naming the approved own home. Confirm the
   same owner remains ready and responsive; no login is performed.
6. Request normal canonical service stop, then observe the retained owner handle
   signaled. Success requires CLI0/stopped as well as physical exit. There is no
   force, terminate, kill, Scheduler registration or uninstall selection.
7. Only after owner exit, open the single own setup journal read-only. Require
   `open=FAILED/PROVIDER_AUTH_REQUIRED`, `possible_effect=true/retry_safe=false`,
   and zero turn action/receipt rows. Publish only this projection, never the DB,
   raw account response, credentials or provider transcripts.

CLI response files remain in the protected own private directory. Public output
is restricted to selected status fields, hashes, own identifiers and failure
codes. EOF/CLI timeouts preserve uncertainty and never trigger a retry or kill.
A failed setup is preserved; running this script again is refused. If an early
start result is lost, the normal stop may still be attempted on that own scope,
but the case cannot claim physical cleanup without its captured owner handle.

## Review map and limitations

- `load`, `write_once`: proposal/runtime pin binding and consumed attempt.
- `environment`, `validate_config`, `validate_account`, `preflight`: isolated
  credential context and finite nonproductive RPC allowlist.
- `validate_review`, `validate_failure`: exact canonical setup scope and diagnosis.
- `ProcessProof`, `journal_proof`: physical exit and post-exit zero-turn evidence.
- `test_run_case.py`: pure negative/positive cases; it cannot prove native behavior.

The pinned 0.157.0 app-server schema declares the `file` credential-store enum in
`ConfigRequirements.cliAuthCredentialsStore`; `Config` allows additional
properties. The actual effective `config/read` value is therefore a mandatory
runtime observation, not inferred from merely writing TOML. Current official
[authentication documentation](https://learn.chatgpt.com/docs/auth?surface=cli)
and [default configuration](https://github.com/openai/codex/blob/main/codex-rs/config/defaults.toml)
support the storage setting; they are not an exact-build runtime result.

This can qualify DX-T34 only if the actual outputs meet the checks. Empty own
credentials do **not** prove SVC-T15's terminal-only credential or locked-vault
case. It does not qualify Scheduler/login, crash/backoff, M1 useful work, native
permission completion or any other acceptance criterion. Existing M1 packages,
homes, services, counters and artifacts remain outside this preparation.
