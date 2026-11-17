# Corrected source supplement — 7 PASS, scoped layers

All seven cases executed, with no skips, errors or NOT_RUN, in 38.574 JUnit
seconds. Source mode is explicit: Nexus imported from the frozen checkout;
Core/Connector imported from the immutable R7 prefix. This is not an installed
Nexus supplement run. All 1,829 source/test pins, 1,031 installed payload files
and the existing fixture helper stayed unchanged during execution.

The initial 6 PASS / 1 FAIL cut remains intact with original test/runner bytes
and separate manifests. Its E16 setup attempted three canonical runtime results
for one operation, violating the schema's unique key. The correction changes
only E16 and imports its existing grouping helpers: three distinct operation,
receipt and capture identities map to the same handoff/claim/workspace, with one
artifact per operation. The resulting logical delivery retains all three exact
artifact references. Its observed `created_at` is asserted to equal the old
receipt timestamp and be more than 24 hours old; age is not inferred solely from
capture time. Seen, off-page isolation, stale-cursor conflict, retained-feed
removal, exact historical target and no inbox ACK/productive mutation all pass.

Limits remain:

- A06 is the real SQLite reader's complete private sibling-proof/filter clause,
  with synthetic historical progress inputs. No lease/authority was fabricated;
  live Working/browser classification is not qualified by this case.
- E08/E09 are actual ASGI/SQLite partial-output assertions over historical
  terminal receipt/capture fixtures, not real native failure or cancellation.
- E16 qualifies three linked artifact references, not managed artifact-content
  retrieval or browser affordances.
- H02 is real HTTP exact-target denial/minimization; H03 is JSON/public-label
  minimization and control encoding, not proof of DOM/ANSI execution safety.
- H07 uses an existing canonical native request and real HTTP stale-decision
  rejection/history reads. The grant revocation is a direct SQL negative-fixture
  change, **not a canonical revocation action or real native lifecycle proof**.
  The same-name successor/browser case remains unqualified.

No product/helper/prefix changed, no provider was invoked, and no complete ledger
scenario is promoted by seven pytest passes. A Root-reviewed narrow gate is
still required before executing these tests against the installed Nexus wheel.
