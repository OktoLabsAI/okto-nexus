# Current Connector integration artifact

Connector **0.0.13**, commit `daa7f2b3abe6aea9ab72338c1475ebbb014a2340`, is
the UI-R1 integration-test dependency selected by `manifest.json`. Its wheel
SHA-256 is `4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90`.
The matching Core **0.0.14** wheel is unchanged (`ea179780...`). Connector is
not a Nexus runtime dependency. No package was published or installed into the
user's personal environment.

This artifact adds the project Resume/Add/Cancel picker and retains canonical
setup, receipt and daemon ownership. Source qualification is in Connector
`docs/evidence/ui-r1/qualification.json`; Nexus installed/browser evidence is
tracked in `NEXUS_UI_R1/execution/`. Source, fixture, installed and native
provider qualification are distinct gates. The existing older wheels remain
historical artifacts and are not selected implicitly.

## Previous integration artifact

Connector 0.0.12 is built from `a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b`,
SHA-256 `2b8ce688541a5ae6e9806467569be0743fef6ff607c763f2b93accf0f93e017d`. Core remains the identical `ea179780...` wheel
pinned by `manifest.json`; no package version or runtime dependency changed.

The Connector retains accepted reconciliation evidence even when no direct
session release was queued, and retires only the exact fenced/stopped opening
with complete event acknowledgment. Unknown owners remain unknown. The source
fix has 46 unique offline cases; this wheel passed 24 focused installed cases.
See `qualification-a8bd48b/` for exact build provenance, installed origins and XML.
No live campaign, provider, release publication or SVC21 acceptance is implied.

## Previous integration record

# CI dependencies for Nexus 0.3.3

Core 0.0.14 is a mandatory runtime dependency. Connector 0.0.12 is used only by
the cross-repository integration tests; it is not a Nexus runtime dependency.
Both wheels are built from the versioned development branches. Connector pins
the same Core version. These artifacts are for validation before publication.

`manifest.json` records their SHA-256 digests. `tools/ci_installed.py` verifies
the hashes before installation and compares installed files with these wheels
before testing. CI uses these artifacts before the matching PyPI versions exist.
