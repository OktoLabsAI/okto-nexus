# Credential stdin consent fix

Connector commit `28e8093997849ba47a018e5d4728f8b3535be4b1` preserves protected credential stdin when fallback storage lacks explicit prior consent. The caller receives `APPROVAL_REQUIRED` before prompting, opening the vault or reading the credential. Backend availability, persisted consent and identity reuse retain their existing behavior; a negative interactive answer stops remote resume before vault access.

Nine new tests and seven relevant regressions passed with Connector source imports and installed dependencies. Independent source/test review found no blocker. These are source checks, not installed-package or live-transfer acceptance. The original qualification predates the commit and remains byte-for-byte retained.

The prior transfer remains `UNCONFIRMED`; its one-time material is not recovered or replayed by this change. No provider, service or personal credential was accessed for this qualification. Scenario statuses remain 125 VERIFIED / 5 IN_PROGRESS / 2 NOT_RUN.
