# M4d4b — Host adoption of physical journal registration

Nexus records an immutable Core location, including server/executor/session
scope, before creating each productive session journal. Server identity is now
part of the selected host composition; a conflicting scope cannot reuse or
retarget its file. The canonical Server catalog and physical registry retain
different responsibilities. Neither registration is proof of native release.

Connector adopts the same port for its shared journal. Retained creation and
global-shutdown tasks protect storage from observer cancellation, scoped
reconnect preserves shared stores, and late compositions cannot publish closed
handles. Its installed campaign passed 118 tests, with one non-Windows skip,
unchanged inputs and exact package bytes; committed/pushed as `5f444c9`.

## Shutdown race found during review

The first Nexus wheel passed 37 installed cases, but a separate adversarial
schedule exposed a gap: shutdown captured `ledger_task=None`, then an already
admitted composition created a ledger. Shutdown joined and removed the runtime
but omitted the late ledger. The installed reproduction observed zero runtime
tasks and a still-usable ledger; a second explicit shutdown cleaned up the
disposable fixture. This was not a production fault injection.

The final host fences ledger access when final storage closure begins. A
delayed composition fails before creating a worker, and ledger-opening errors
follow the same effect-free cleanup path as other composition failures. The
final fence is monotonic: a later containment-only pass cannot reopen access.
The initial containment phase still permits final history/publication work.

Qualification records are in `m4d4b-results.json`. The final campaign exercises
registration, retained cancellation, late creation, failed ledger construction,
monotonic closure, capacity, technical Pi child processes through both hosts,
and the six initial-refusal restart boundaries. The separate before/after
reproduction uses the installed package and a disposable temporary store.
It is not claimed as the cause of the user's simultaneous Recovering report.

## Evidence and limits

The initial installed campaign passed 37 cases; the final campaign passed the
26 cases affected by the additional shutdown fix, with no failures or skips.
Both campaigns verified exact installed packages and unchanged inputs.
Unchanged catalog SQL and
its 1k/10k/100k measurements are retained from the first campaign; they are not
presented as a second run on the final wheel. Reports:

- `build/runtime-m4d4b-host-installed/{campaign.json,installed.json,tests.xml}`.
- `build/runtime-m4d4b-final-installed/{campaign.json,installed.json,tests.xml}`.
- `build/m4d4b-late-ledger-source.xml` (11 focused source cases).
- `build/m4d4b-late-ledger-reproduction.json` (failing initial artifact).

The exploratory source campaign first failed two capacity fixtures lacking the
canonical database and one technical Pi Connector case waiting for a native
action. The fixtures now use the real migrated database; the unchanged Pi case
passed in the joint installed campaign. No timing-root-cause fix is claimed.
Installed warnings concern Starlette test transport deprecation and JUnit
property formatting; recorded SQL properties were inspected. A 120-second
faulthandler diagnostic occurred while inserting the 100k fixture, not while
the recovery algorithm was running; the original process completed normally.

Core's additional three installed cost cases (`4ea0dab`, unchanged M4d4a wheel)
show constant registry lookup/page VM work. Registry-only allocation at 100k
representative locations is 43,925,504 bytes. Combined capacity/slot metadata
budget remains unqualified; see `m4d4-store-audit-design.md`.

Final artifacts:

| Package | SHA256 |
| --- | --- |
| Nexus 0.3.1 | `95fe2fda95e4cc0c3c32fb492ba1e62ea1f9d514340bd5fcef2a3c6a5fe985b3` |
| Core 0.0.12 | `e93dc1e1cdcc5d0868265c36c0e1200a1ff048aa79371e410727b3dfe74cad3b` |
| Connector 0.0.10 | `2e222043b889314a21492191a77b41b1ba890f1a8cc12b3885efecc651ce0893` |

All 547 Nexus package files match the final wheel. Qualification uses the
isolated `build/m3k-owner-env`, not the global installation. No real-provider
UI gate or global rollout is claimed for this technical checkpoint. Production
generation 73 is preserved. The old startup directory audit remains: first
audit frontier, restore/reset invalidation, scan caps, stream fairness and the
remaining full-plan gates are still pending.
