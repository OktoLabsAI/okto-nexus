# TR4-14-02 authority uncertainty and revocation recovery

## Defect and correction

The normative entry point `tests/execution_r4/test_ns14.py::test_ns14_02` exposed a lost-acknowledgement defect in Core 0.2.50. A revoked durable row fenced the native binding, but the conservative in-memory context retained its earlier authorization revision. Repeating the original R4 revoke then returned STALE_GENERATION instead of acknowledging the already committed revocation.

Core 0.2.51 recovers that acknowledgement by reading the exact session's durable row and comparing all fence fields: revoked, connection generation, owner generation, authorization revision and configuration revision. A missing or mismatched row cannot produce the acknowledgement. The comparison does not import permissions, identity or deadlines from storage. No second CAS is sent after a confirmed matching revocation.

## Normative test

The unit-contract scenario starts a runtime through the canonical public Nexus binding/admission flow and uses its actual embedded executor and Core journal. Four cases cover:

1. A durable generation advances beyond the renewal's expected generation. CAS loses; the old context performs no native sends.
2. Renewal confirmation fails before commit while the durable read is unavailable. A completed producer and elapsed time leave work restricted. Restoring the unchanged full row proves rollback and allows exactly one native send under the original authority.
3. The durable read remains unavailable. Work remains restricted after the producer concluded; no timeout fabricates rollback.
4. Revocation commits but its acknowledgement is lost and the durable read is unavailable. Old authority performs no native sends. After storage recovery, the same revoke is acknowledged without a second CAS.

Six directed Core cases independently verify the matching row and mismatches in each of the five fields. In every mismatch case, the acknowledgement is refused and old native work remains fenced.

The initial test run also contained a fixture error: the proposed renewal exceeded the allowed maximum lease window and never reached CAS. The proposal was adjusted within the same configured limit, and the test now asserts the error occurred at the intended storage/CAS stage. The original failing evidence, including resulting fixture teardown errors, is retained rather than counted as product acceptance.

## Artifact and acceptance scope

Nexus and Connector pin the same Core 0.2.51 wheel. The installed runner checks source/wheel/installation bytes for all three packages and runs Core lease regression, Connector execution/admission, Nexus canonical lease/capability recovery, inventory and both NS14 normative tests. See test_runs_20261001_ns14_02.json for exact results and hashes.

TR4-14-02 is qualified at its unit_contract layer on the installed Windows tuple. This does not close all of NS14.02: NS14.01 remains unverified in the acceptance inventory, and complete rotation/revocation coverage across every online surface, remote expiry and final platform/provider acceptance remains open. No release gate is closed. Existing UI assets and older actual-provider evidence retain their recorded scopes.
