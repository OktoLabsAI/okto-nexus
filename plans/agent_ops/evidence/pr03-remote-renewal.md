# PR-03 — remote grant renewal and credential replacement

Status: implemented and verified for the Windows loopback contract below. Full PR-03 and R3 remain IN_PROGRESS.

Remote grant renewal is qualified with real loopback HTTP/WebSocket, authenticated TCP IPC and DaemonApp: expiry/exhaustion, lost issuance response, same-receipt recovery, unchanged prior leases/sessions, explicit close/new work, canonical key rotation and protected replacement, stale key/ticket/review refusal and historical recovery after revocation. Completed Connector reuse authenticates the current identity and exact approved binding without mutating the old bootstrap or replaying Finish/probe; pending setup remains anchored to its original credential epoch. Submitted issuance stays uncertain during login/vault/recovery failure; a transport failure reading an already confirmed receipt does not reopen issuance uncertainty. Installed tests: Nexus 66, Connector 233. Native/provider behavior remains synthetic; real provider/TLS/two-host, OS-vault lifecycle, native services and complete M1/M2/R3 remain open.

## Delivered behavior

- Reuse after explicit key replacement is limited to a completed configuration, one APPLIED intent and the exact current APPROVED binding. Current Server/agent/origin, local installation/configuration, consent, child map, proposal and Finish result must still agree. No pending local review or unfinished startup operation may enter this path.
- The Connector checks authenticated current identity and binding, then rechecks retained host facts before daemon effects. A concurrent identity/profile/root/intent/binding or physical selection change refuses reuse. The old bootstrap epoch is historical; it is never rewritten or accepted to finish a pending setup with another key.
- The existing key rotation endpoint and `identity replace-credential` remain explicit. Rotation is one-shot and has no automatic retry guarantee. Reconnect does not issue grants, repeat probes or submit work. Current revocation and policy remain authoritative.
- Existing human `work authorize` review/issue/recover APIs remain unchanged. A submitted issuance stays `unconfirmed` on login, vault or recovery failure. A confirmed receipt's read-only recovery cannot make the issuance uncertain again merely because the transport labels POST failures as possibly effective. No new API, migration, authority or Core protocol was introduced.

## Qualification

| Package | Version | Installed tests | Exact package files | Wheel SHA-256 |
|---|---|---:|---:|---|
| Nexus | 0.3.3 | 66 | 690 | `5ddbbc782d9f81f1db6b257c25e0e8c1df12bc8ea586ba5a0060e74eb60c1ae7` |
| Connector | 0.0.12 | 233 | 123 | `a8cf18105fa1cdca0443b6a3be08972d5576f72f3ce07e5a19dd9fc7cd59ae5a` |
| Core | 0.0.14 | exercised by both suites | unchanged vendored wheel | `5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb` |

Both declared installed suites pass without failure/error/skip, outside the checkouts with noneditable-wheel and module-origin guards. Nexus candidate-v2 reuses the exact Connector wheel qualified in candidate-v1. Candidate-v2 adds only the final correction to confirmed receipt recovery in Nexus; the final Nexus suite includes the joint four-case campaign and all 19 uncertainty cases. Source/build/wheel/install file hashes match the final product. There is no registry publication or merge.

The four joint cases use the actual Server, Connector DaemonApp, real authenticated loopback TCP IPC, control/heartbeat, inventory barrier, WebSocket dispatch, Core storage, human OperatorProfile and canonical APIs. They cover:

1. Naturally exhausted grant and an explicitly expired grant fixture. Loss is injected after actual issuance commit; reopening the work checkpoint recovers one grant/receipt without another issue. Existing sessions, leases and operations remain unchanged until an explicit close. Separately requested new work uses the new grant.
2. Explicit canonical rotation and protected Connector replacement. Old key and derived ticket are refused; a stale grant review conflicts. Completed reconnect preserves binding, bootstrap, proposals and Finish records without another probe. Fresh inventory/authority admit separately requested work with the current epoch.
3. Revocation before review and after uncertain issuance. Recovery returns historical metadata without reactivating the grant; participant key requests to review/issue/recover are refused.

Expiry is created by changing only the isolated grant expiry after a real first operation; clocks, tickets, leases, capacity and admission are not extended or bypassed. Native process/provider responses and discovery/probe effects are explicit doubles. The daemon runs foreground inside the test, and the spawn request reuses that owner; no Windows service is installed. Operator storage is an isolated memory vault and host storage an explicitly approved restricted temporary file vault.

Source qualification has 19 new operator cases, 37 existing authorization/operator cases, 6 existing CLI cases and 4 joint cases. Connector has 233 unique qualified cases, including 28 new cases. Source reports overlap with installed runs and are not added to installed totals. Initial failures remain recorded: the intended epoch mismatch; a CAS error-code expectation; uncertainty classification; and integration fixture assumptions about IPC selection, readiness, inventory, operation stage and grant accounting. `source/integrated/campaign-summary.json` gives exact attempts and limits. Public copies redact synthetic credential literals; raw reports remain outside the repository, with original/public hashes and redaction counts in `reports.json`.

Full Ruff checks pass for the changed product/new test files, and tracked/untracked whitespace checks pass. No already-closed bootstrap evidence was changed. This milestone does not qualify OS-vault access, real native/provider context, service login/logout/crash/reboot, two physical hosts or productive M1/M2. Those limits do not change the fixed plan or its acceptance criteria.

Usage: [terminal work](../../../docs/terminal-work.md), [remote setup and completed reuse](../../../docs/remote-project-setup.md). Evidence: [reports](pr03-remote-renewal/reports.json), [artifact manifest](pr03-remote-renewal/artifact-manifest.json).
