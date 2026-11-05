# PR-03 — Connector login startup in the initial review

Connector connect/configure now offer login startup in the same local connection confirmation, with a secret-free instance/context review and an independent durable host checkpoint before native effects. Existing installer/lifecycle contracts perform drain, install or enable, and supervised readiness before remote onboarding continues. Resume preserves the original request and refuses conflicting choices; reconnect preserves later disablement/removal. Operator approval remains the separate authority for remote execution. 74 focused source tests passed before the final JSON-mode guard; 152 Connector and 104 Nexus tests passed against the final installed artifacts. DX-T37 review/decline is verified for the declared Windows contract with injected native effects; actual login/logout/crash/credential qualification and full productive M1 remain open.

Both `connect` and Connector-hosted `configure` offer the local startup choice.
`--start-at-login` preselects it; `--no-start-at-login` keeps the current service
mode. The final human confirmation names the effective user, instance, state
directory, interpreter, working directory and controlled transition. Long paths
are displayed in full. Canceling before Finish has no native effect; declining
preserves on-demand use and any existing task.

The saved local request includes a secret-free plan revision and pending host
intent before native calls. The existing UserService, service_install and daemon
lifecycle implement the effects. Installation can drain the current Connector;
no forced termination or replacement process is introduced. A separate installed
checkpoint allows readiness recovery without repeating registration. An unknown
native registration is not adopted/recreated. A lost enablement response resumes
only the retained enablement intent. Context or explicit project/installation/
startup changes are refused before recovery.

The reviewed host effect takes place before remote registration/proposal and is
independent of Nexus operator approval. Local startup plans are excluded from the
portable configuration and proposal. Background completion preserves the local
checkpoint. Completed reconnect never reinstalls/reenables a task later changed
by the user; current observed startup is reported separately from the old intent.
Server-hosted configure refuses the local task option. Interactive connect now
rejects JSON mode before credential access, matching configure, so its human
confirmation cannot hide the startup review.

## Evidence and limits

- Source: **74 passed**, including the 14 new wizard/lifecycle cases,
  background checkpoint preservation, R4 forwarding, existing configuration and
  user-service regressions. This source run predates the final JSON-mode guard.
- Final installed Connector: **152 passed**, no failures/errors/skips.
  Includes the final JSON guard, native installation/enablement/recovery,
  service upgrade/readiness/reconnect and disposable real detached processes.
- Final installed Nexus: **104 passed**, no failures/errors/skips.
  Includes local login review/decline/recovery, terminal setup, remote operator
  sessions, real HTTP/SQLite binding approval plus Connector background apply,
  and existing service routing. Reports overlap and are not summed as unique cases.
- Installed CLI help exposes both choices; actual `connect --json` refuses before
  credential/native effects. Ruff E9/F, whitespace and the fixed R3 ledger are
  checked before commit. All **431/116/130** package Python payloads match source
  bytes; imports under `python -I` resolve to the isolated installed environment.

Campaign: `C:\Users\jpamb\AppData\Local\Temp\r3-connector-login-var8f08z`.
Connector source commit: `85dcf0505d34973f59c0a6c5bc84636e8c3a0dc1`.
Connector wheel SHA-256: `b97b3cfaa90fc843d4e1f925f895af2ea59060f5fe554a23a68390c22c144369`.
The same tested wheel and hash replace the Nexus CI pin. Nexus production source
is unchanged; its prior qualified wheel was reused after byte-for-byte audit.
Core source/version/pins are unchanged. Package hashes are in the companion JSON.

The new wizard tests use real StateStore preference writes, real lifecycle and
installation receipts, with network onboarding peers, native Task Scheduler and
process/IPC observations injected. They prove review ordering, persistence and
recovery, not an actual logon or a real provider turn. Existing process tests use
disposable directories. No personal service, native task registration, real
credential access, paid inference, package release or merge was performed.

DX-T37 is verified for the Windows review/decline contract in both components.
SVC-T18 and real login/logout/crash/credential campaigns remain NOT_RUN under the
unchanged campaign approval request. POSIX native qualification, new remote
identity/unified setup, productive M1, participant initialization, preset
evolution, dashboard introduction and later ATN/OBS scope remain open.
