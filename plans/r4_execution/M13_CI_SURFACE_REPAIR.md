# MCP surface and installed CI corrections — October 2, 2026

The Linux/Python 3.12 full regression at `0e9274b` remains a failed campaign
(43 failures and one error). This change addresses a subset of those findings;
it does not replace that campaign or close M13/G0–G3.

## Corrections

- Seventeen harness parameters now describe their R4/legacy meaning in the
  generated MCP schema. Three tool summaries meet the existing 200-character
  limit. Surface revision is 64; identity resource content remains v30.
- `message_create` documents its mutually exclusive local-path/workspace-ID
  selectors. The schema test accepts either selector, including remote workspaces.
- Surface measurement selects the existing approved growth allowance from the
  actual registered tools. Baseline, budget and approved growth values are unchanged.
- Historical feature tests verify their minimum introduction revision and/or the
  current advertised revision; the identity/cache test pins the current revision.
  Migration tests retain rollback, backfill and repeatability assertions while
  including all currently shipped migrations after version 58.
- The isolated installed runner preserves declared pytest markers without
  importing the checkout through pytest's `pythonpath` setting.
- Two subprocess checks invoke the tested interpreter directly, removing a local
  RTK executable dependency from hosted test environments. Shell work still uses RTK.
- Hosted checkout fetches full history for the existing NS00 ancestry assertion.
  Local success does not prove the hosted checkout change until CI runs it.

## Verification

An isolated frontend/package build produced development artifacts:

- Wheel SHA-256: `a6f3edf88fc752e1065c2a58f2caa9daa02926b59a202dfc41c4098acedfec8c`.
- Sdist SHA-256: `65ffdabf674422032a002ad72be7f618208c44af41730607ec211da900a9e290`.

After installing that wheel, **59 tests passed and one was skipped in 80.64 s**
on Windows/Python 3.13.1. The runner verified Nexus/Core/Connector package bytes
against their wheels and recorded no changed campaign inputs. Tests cover tool
schemas, compaction, budgets, resource/cache identity, historical feature checks,
migrations, marker registration, native-loader retirement, NS00 ancestry,
NS15.03 REST/MCP and retired-stdio recovery with active HTTP ownership.
The existing manual/probabilistic assertiveness test remains skipped.

Evidence: [campaign](evidence/ci-surface64/campaign.json),
[JUnit](evidence/ci-surface64/tests.xml),
[installed hashes](evidence/ci-surface64/installed.json), and
[isolated build manifest](evidence/ci-surface64/build-manifest.json).
The initial source run (37 passed, one failed, one skipped) is retained: its
new selector assertion exposed missing exclusivity wording, which was corrected.
The subsequent source check passed 25 tests with one skip.

## Remaining findings

Presence/trust fixtures lack the current admission fence; their ACK failure still
requires directed diagnosis. Retired-stdio positive execution tests, legacy native
constructor expectations, constructor-time revocation and the NS14 load/SQLite
locking failure remain unresolved. Full hosted regression, final immutable tuple,
complete UI/CLI/fault/platform acceptance and independent hosts remain open.

Connector issue [#1](https://github.com/OktoLabsAI/okto-nexus-connector/issues/1)
was rechecked: it is still the only open issue. Discovery diagnostics and explicit
platform documentation are included in prior Connector corrections; macOS managed
execution remains unsupported. A zero-candidate discovery result concerns local
provider installations, not Nexus/LAN discovery or successful host connectivity.
