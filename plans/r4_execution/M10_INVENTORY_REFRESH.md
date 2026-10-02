# M10 — Correlated passive inventory refresh

Status: durable queue, embedded consumer, negotiated remote HTTP delivery and UI
implemented. Independent-host/full-platform acceptance remains open. No gate is closed.

Migration 097 stores requests by Server, authenticated actor and client intent.
Replays revalidate current credentials and executor visibility before returning
the same refresh ID. Each executor has at most 32 pending requests. Completed
requests remain durable for replay; this increment does not define retention.

A current executor generation claims a batch before observing installations.
The delivery records its producer, generation and baseline publication sequence.
Only a correlated, newer publication completes the batch, in the same transaction
as the snapshot. Periodic publications without that correlation cannot complete
a request. A rejected correlation rolls back the snapshot too. Requests arriving
after a claim wait for a separate observation. A successor generation receives a
new delivery; the old producer cannot acknowledge it.

The embedded owner now claims before passive discovery, revalidating its store
lease and executor ownership. Initial RECOVERING startup still publishes its
baseline first. Once CONTROL_READY, the existing 30-second refresh loop consumes
pending requests. Failed discovery leaves the same delivery pending for retry.
Canceled observers and shutdown retain the existing owned discovery/publication
tasks. Refresh creates no session, launch consent, binding or execution lease.

## Initial queue/embedded verification on 2026-10-02

- Source: 16 queue/embedded cases passed.
- Installed Windows/Python 3.13.1: 33 passed in 86.10 seconds.
- Installed WSL Linux/Python 3.12.13: the same 33 passed in 86.74 seconds.

Installed campaigns include queue authorization, restart/idempotency, capacity,
generation changes and rollback; real serve lifecycle with synthetic passive
discovery; a request inserted during a held scan; failed-scan retry; shutdown
storage ordering; and migration checks. They import application packages outside
the checkout with `-I`, verify installed package bytes and unchanged campaign
inputs. These are existing test environments, not the final clean-install M13
campaign. No real provider or independent remote host was exercised here.

Development wheel SHA-256:
`ebb83be70f649cc401e81733e500d6dac068c02faecb9c6303eef21db2060519`.
Sdist SHA-256:
`5071e259b9544a24ef29492b5097e5af2976f3fdcfb6da6b7cc7eb674e49f8f6`.
The build manifest records base HEAD `46b09b3` plus exact working-source hashes;
it is not an assertion that that old commit contains this implementation.

[Build manifest](evidence/inventory-refresh-local-build.json),
[Windows campaign](evidence/inventory-refresh-local-windows/campaign.json),
[Linux campaign](evidence/inventory-refresh-local-linux/campaign.json),
[source report](evidence/inventory-refresh-embedded-source.xml).

Reproduce after installing this wheel and the pinned Core/Connector test wheels:

```powershell
python tools/ci_installed.py test --wheel PATH_TO_WHEEL --output NEW_EVIDENCE_DIRECTORY --tests tests/execution_r4/test_inventory_refresh_queue.py tests/execution_r4/test_embedded_inventory.py tests/execution_r4/test_shutdown_storage_order.py tests/test_migrations.py
```

## HTTP and daemon integration on 2026-10-02

`POST /v1/runtime/executors/{id}/inventory:refresh` now returns the scoped view
with status 202. Repeating the same actor/intent reads its current state. Unknown
fields/query parameters are refused and queue capacity maps to HTTP 429.
The executor-only `inventory:claim-refresh` route verifies the control ticket,
then rechecks its scope, expiry, credential/authorization epochs, revocation and
current connection inside the claim transaction. The inventory publication path
shares that authority validator. Correlation uses `X-Nexus-Inventory-Refresh`;
the Core snapshot and WSS schemas remain unchanged.

Protocol metadata advertises `inventory_refresh_supported`. The documented
ProtocolInfo schema was reconciled to the actual R4/Core .53 response, including
format 2 and existing readiness/limit fields. The optional extension is strictly
boolean; older Servers do not cause new Connectors to poll an unsupported route.
Connector `c110246` claims before discovery at startup and every five seconds
while connected. See its
[implementation and evidence](https://github.com/OktoLabsAI/okto-nexus-connector/blob/c110246/plans/implementation/INVENTORY_REFRESH.md).

The first source HTTP run recorded one test expectation error: the existing
request-validation handler returns 400 for unknown body fields, not 422. That
expectation was corrected; 13 source regression checks then passed, followed by
four schema/OpenAPI checks. No product validation behavior was weakened.

Both new packages passed installed acceptance on Windows/Python 3.13.1 and WSL
Linux/Python 3.12.13: 26 Nexus checks on each (75.47 and 84.33 seconds), and 79
Connector checks on each. Nexus campaign inputs stayed unchanged. The tests cover
real WSS reconciliation plus HTTP request/claim/publication, same-sequence replay,
invalid-correlation rollback and revocation between ticket verification and the
claim transaction. The actual daemon's HTTP/WSS/IPC lifecycle completes an offline
request on startup and another online request after reconnect. No operation or
session is created. Discovery is empty/synthetic; both roles run on one machine.

New development artifact hashes:

- Nexus wheel: `2edfbcfb5f1076b5587a3b4c8d1fd50aa8e6f105168a54d0a1f7d4302b7704f4`.
- Nexus sdist: `86cbb2668ed497c9f8868f1a462564ec2f60d6cc21910ff06c71b91ac6aefe88`.
- Connector wheel: `46991823a500fef326917edeb6063fb6e570126731e35d8c9c349104a1740b8f`.
- Core wheel unchanged: `cc873031378793d374a9bbc00572c7a525f99c4246324a941713d866cc62c6b1`.

[Build manifest](evidence/inventory-refresh-http-build.json),
[Windows campaign](evidence/inventory-refresh-http-windows/campaign.json),
[Linux campaign](evidence/inventory-refresh-http-linux/campaign.json).
The new Connector wheel is pinned in the CI manifest; these are development
artifacts with verified installed bytes, not final frozen commits or clean-env
M13 proof. The previous Connector hosted run has two unresolved Windows renewal
timeouts despite passing directed tests. Full hosted qualification remains open.

## Dashboard integration on 2026-10-02

The selection panel now has separate read-only reload and host-refresh controls.
It resolves the authenticated Server/actor identity before persisting an intent
in sessionStorage, scoped also to the executor. It persists before POST, reuses
the ID after an uncertain reply, resumes pending requests on remount/reload and
polls every five seconds. Host changes abort the old observer without discarding
its request. UPDATED clears the stored request only if it still matches, clears
the prior installation selection and reloads current choices. No credential is
stored in the refresh record and no execution operation is requested.

TypeScript compilation passed. Two source browser cases passed. The first enabled
source run had the five-second poll racing Playwright's default five-second
assertion limit; the database already recorded completion. The assertion now
observes up to three poll intervals without changing production timing.

The installed Windows/Python 3.13.1 Edge campaign recorded nine passes and one
test-only strict-selector failure: both theme logos share alt text. The selector
was corrected to the visible accessible image and that case passed separately
in 13.81 seconds. The retained reports distinguish the initial failure from the
successful follow-up; both campaigns had unchanged inputs. The new case uses
the actual API, loses the first response after durable acceptance, retries the
same ID, switches between offline remote and live embedded executors, completes
the local observation, reloads the page and proves only two requests/no operations
exist. Assets come from the installed package; HTTP is bridged through TestClient,
SSE is excluded and discovery is synthetic/empty. This is not independent-host,
Linux-browser or real-provider UI qualification.

Nexus UI wheel: `62121869d6a19b374d61eab513b03d3bdc42973b6d6567e03620b621c869dcf0`.
Sdist: `defc9cf627606b9e625133b7172c1a017a4b8c1ec291383215d778a169d03718`.
Core and Connector pins are unchanged from the HTTP campaign. The dashboard was
built outside the checkout's static tree, preserving preexisting user assets.

[Build manifest](evidence/inventory-refresh-ui-build.json),
[initial installed campaign](evidence/inventory-refresh-ui-installed/campaign.json),
[corrected browser campaign](evidence/inventory-refresh-ui-installed-fixed/campaign.json),
[reviewed screenshot](evidence/inventory-refresh-ui-offline.png),
[updated-guide audit](evidence/inventory-refresh-ui-ns15-docs.json).

Reproduce with the new wheel installed, Playwright and Edge available, and
`OKTO_NEXUS_UI_CAMPAIGN=1` plus `OKTO_NEXUS_UI_INSTALLED=1` in the test environment:

```powershell
python tools/ci_installed.py test --wheel PATH_TO_WHEEL --output NEW_EVIDENCE_DIRECTORY --tests tests/execution_r4/test_inventory_refresh_dashboard.py tests/execution_r4/test_runtime_selection_dashboard.py tests/execution_r4/test_binding_consent_dashboard.py tests/execution_r4/test_inventory_refresh_http.py tests/execution_r4/test_packaged_openapi.py
```

## Remaining acceptance

The [NS15.05 supporting documentation audit](evidence/inventory-refresh-ns15-docs.json)
passed against the installed Nexus package and updated guide. It checks command
help, documented routes and links; it does not prove browser or final-artifact
scenario acceptance.

Exercise independent-host/provider/fault acceptance on final packages and complete
the broader onboarding/runtime UI journeys. Full browser/platform support,
NS15.05 closure and M13/G0-G3 are not implied by these directed tests.

Connector issue #1 was rechecked and remains the only open issue. Its documented
unsupported macOS managed-runtime state and Linux-guest workaround remain the
accepted implementation path; no macOS containment qualification is claimed.
