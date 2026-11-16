# HOME-R1 direct-operation namespace correction

The real migrated-SQLite fixture contains two executors under one server. Both
have a `turn.submit` with the same local operation ID, separate sessions and
SUBMITTED receipts. Neither is asserted to be running.

The retained before run fails three checks: the two activities have the same
Home ID, the second one is lost on a one-item keyset page, and an actual
canonical Attention occurrence for executor A is also attached to executor B.
The occurrence is produced from A's RECONCILING dispatch row using the existing
Attention projection and epoch trigger, not a fabricated Home DTO.

The correction adds executor and session to the Home ID for direct operations
only. Handoff and conversation identities remain unchanged. The direct source
match for Attention now requires the executor/session too; the existing runtime
reference match already required them. Opaque source IDs and canonical targets
remain unchanged. This clarifies Home v1 identity and introduces no protocol,
migration, domain mutation or new authority.

The final run includes all three namespace cases and existing native-question
projection regressions. No provider, live service or native runtime ran. Earlier
wheel/CLI qualification remains tied to its old source snapshot; this evidence
does not promote the corrected source to an installed package.
