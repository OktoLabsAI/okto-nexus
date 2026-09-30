# M06 — Automatic runtime lease renewal

Status: partial implementation of the fixed delivery plan. No milestone or gate closes here.

## Behavior

The automatic Connector owner renews each live session at half of its remaining Core lease budget. A bounded group of eight renewal requests leaves transport capacity for controls. The owner revalidates persisted binding, profile, identity and current lane before requesting and before installing authority. Only the Core-installed deadline advances the schedule. A refusal fences the connection without replaying native opening or extending the old deadline.

Concurrent productive operations share a gate; renewal waits for their native calls to finish and holds subsequent productive calls until installation completes. Interrupt, close and non-permissive native replies retain their containment path. Shutdown retains an in-flight renewal producer even if the cleanup observer is canceled.

For exactly compatible renewal on the same channel, Nexus retains the previously applied lease until the new application ACK commits. Dispatch and session capabilities use this applied authority with its original expiry and existing current-authority checks. Different scope, channel, source grant or action set cannot borrow the old authority. The new ACK supersedes the old serial and updates capability expiry in the same transaction.

Core 0.2.38 publishes the R4 context together with the session context after the durable lease CAS, before inspection or event persistence can yield. Productive work remains blocked while installation is pending. A containment caller that captured an older context receives an explicitly safe pre-effect refusal; Connector may retry once with the current context and the same operation ID.

## Faults found and resolved

- An issued compatible renewal previously set LEASE_PENDING and superseded the applied lease before ACK, causing admission or dispatch to stall.
- Core session and R4 contexts briefly disagreed during post-CAS event persistence. A safe retry classification alone did not resolve that window. The initial installed Nexus campaign retained below reproduces this failure; publication is now synchronized.
- Capability authorization selected the newest issued lease instead of the still-valid applied lease. Tools and metadata now use the same effective applied lease; expiry and revocation remain enforced.
- The older pending-containment test expected SUBMITTED from policy close. Its assertion now matches the already-established terminal SUCCEEDED contract.

## Evidence and limits

The installed runner checks package bytes against source and wheels, imports from site-packages, and verifies the shared Core version. Raw initial results remain separate from the final campaign. The remote integration uses real HTTP/WSS, Server-issued grants, automatic daemon renewal and a technical native peer. It waits beyond the initial Core deadline, then exercises control and close with one native opening and no duplicate dispatch attempts.

The provider probes use real local Pi, Codex and Claude through the installed production Core factory with locally constructed R4 grants. They cover one model turn, renewal to serial 2 and terminal close. They do not establish complete Server-issued provider journeys.

Full ticket rotation, live-session adoption, embedded automatic renewal/publishing, cold process-kill recovery, complete UI/CLI journeys, migrations and final Windows/Linux/independent-host acceptance remain governed by DELIVERY_PLAN.md. Existing user UI assets are present in the Nexus wheel but are not committed or accepted as UI delivery by this increment.

## Installed results

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Core | 154 | 0 | 0 |
| Connector | 417 | 0 | 1 |
| Nexus | 144 | 0 | 0 |

Pi 0.87.1, Codex 0.159.0 and Claude 2.1.282 each completed a real turn, renewed to serial 2 and persisted a SUCCEEDED close receipt without a close error.

Core commit: fb4c8df70a66b9d9df7729fee5cbff453b591d31.
Connector commit: cba635a714f0f0c998badf4f075713a22b862d7d.
The Nexus commit is the commit containing this document.

Shared Core wheel SHA-256: f9bc5c3002593845416187b91802dfe914fd89b04036fd699be48e81dfff321b.

[Result manifest](test_runs_20260930_lease_renewal.json),
[artifact manifest](evidence/lease-renewal-artifacts.json),
[installed runner](run_lease_renewal_installed.py),
[provider runner](run_lease_renewal_providers.py).
The raw JSON/XML/log evidence uses the lease-renewal prefix; initial results use lease-renewal-initial. Do not add initial and final counts as distinct coverage.
