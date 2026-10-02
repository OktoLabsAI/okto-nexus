# M10 — Correlated passive inventory refresh

Status: internal queue and embedded consumer implemented; public HTTP, remote
Connector transport and UI integration remain open. No gate is closed.

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

## Verification on 2026-10-02

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

## Remaining integration

The planned `POST /v1/runtime/executors/{id}/inventory:refresh` is still absent.
Wire that route to the scoped service, add authenticated remote claim/publication
correlation with transactional ticket revalidation, negotiate HTTP capability,
and make the Connector claim before discovery. Then integrate UI request/status,
exercise offline/reconnect/lost replies through real transports, rebuild both
packages, and run independent-host acceptance. Do not add fields to Core's closed
snapshot or pretend that a periodic publication acknowledges a user request.

Connector issue #1 was rechecked and remains the only open issue. Its documented
unsupported macOS managed-runtime state and Linux-guest workaround remain the
accepted implementation path; no macOS containment qualification is claimed.
