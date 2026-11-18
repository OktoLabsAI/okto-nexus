# SI-019 presenter credential and writer fence

Migration 180 adds independent presentation records and a durable writer epoch per canonical session. Read-only review returns the current epoch and occupancy. A write preparation freezes the reviewed epoch and explicit takeover choice. A repeat of the same intent returns its receipt without reconstructing the ticket.

The internal broker issues a short ticket for an exact session, operator authority, capability revision, and transport audience. The broker binds one challenge to the trusted channel. Successful activation consumes both secrets and retains their hashes only until consumption or expiry. Active checks revalidate the original operator and current capability. Concurrent activation is serialized by SQLite and protected by a unique active writer index. Takeover replaces the prior presenter in the same transaction. Readers remain independent. Detach and a trusted channel disconnect only change presentation state.

The two leases are independent. The presentation offer lasts 30 seconds and an attachment lasts 120 seconds in the broker instance's monotonic clock. The original authenticated channel can refresh a current presentation after revalidation. Refresh updates only the presentation deadline. A new broker instance fences prior presentation records and retains the highest writer epoch. These values and the wire exchange still need qualification in the client transport.

## Evidence and rollback

The synthetic transport tests cover scope and generation isolation, one-use tickets and challenge, wrong audience and transport, changed intent, revoked login, concurrent writers, explicit takeover, independent readers, detach, capability drift, expiry and broker restart. They also verify that presentation preparation creates no R4 operation. The migration regression applies 180 with previously recorded queue and control data and checks that it creates no inferred presentation records.

The execution and session interaction regression run passed 110 tests. The final focused run passed four tests after adding the missing capability revision guard. Strict Twine checks passed for the wheel and sdist. The wheel contains the broker and migration byte for byte. Its SHA-256 is `31aec98a0d1145310a6d929a6872650fe62fcc757afb2a5c2f8d80d147c528ed`.

The follow-up adds a writer check for use inside the same authenticated transaction as canonical intake. The synthetic test took over the writer after a successful preliminary check. The former writer could not enqueue, and the current writer could. A read transaction cannot use the effect check. A second test refreshed a reader without extending a productive lease or creating an operation, and refused a wrong channel, revoked login and expired presentation. The session interaction regression passed 97 tests, and strict Twine checks passed for both archives.

This internal increment grants no browser or terminal connection. The future transport must supply the authenticated channel and audience, enforce the native method allowlist, and use the current host proof before forwarding effects. A schema-180-compatible build can disable the broker while retaining its records. The plan remains in progress.
