# R3 — service startup boundaries

Occupied HTTP ports previously caused a real nonzero startup exit but exposed only
STARTUP_FAILED. The Server now records PORT_IN_USE (or BIND_FAILED for recognized
address/permission failures) in its bounded public lifecycle log. Classification
uses the actual asyncio listener exception and numeric errno, never arbitrary
exception text. No fallback endpoint/database and no takeover were added.

Only Nexus changed: serve.py, the log-code allowlist, seven new cases across two
test modules, and service documentation. No schema, wire or dependency change.
Rollback is the Nexus commit revert; this change writes only existing log records.

Before: the installed baseline ran seven cases, six passed and the occupied-port
public-diagnostic assertion failed. Earlier fixture/preparation failures remain
in before/ with their original results and manifest. After: **21 unique tests
passed** in a newly installed noneditable wheel environment: seven new cases and
14 reused log/lock cases. Core/Connector stayed at their qualified baseline wheel
hashes. The frozen snapshot excludes concurrent drain implementation work.

The canonical ci_installed.py runner verified installed bytes and unchanged test
inputs. package-proof.json compares all 690 Nexus payload files with the wheel,
installed files and frozen source; Core165 and Connector123 files match their
wheels. pip check and Ruff on the four changed code/test files passed. Commands,
distribution versions, XML, hashes and environment allowlist are retained.

SVC-T06/T12/T13 are verified for these Windows disposable-process contracts,
composed with the existing timeout observer test. Ctrl+C was injected at the
connect wait callback, not broadcast as a console signal; the actual service
owner remained unchanged and subsequently reached READY and DRAINED. This is
not a logon, logout, reboot, Task Scheduler, provider or full M1/M2 campaign.
No native service was registered and no personal vault/configuration was used.

SVC07 drain/explicit-force implementation remains the next dependency. Its new
three-repository payload must be built and qualified separately. The prior native
service proposal must be reconciled with that payload before any authorized run.

Git stores serve.py and the boundary test with LF while their qualified Windows
working copies contain CRLF. git-source-equivalence.json verifies exact normalized
content and retains both hashes; the wheel/input hashes are not rewritten.
