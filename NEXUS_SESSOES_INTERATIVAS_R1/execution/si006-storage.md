# SI-006 first SQLite increment

Migration 169 adds an input ledger and sequence per exact R4 session key.
It does not update old rows or migrations. Input identity binds the actor's
opaque authority reference and stable intention ID to exact scope, owner
generation, mode and text fingerprint. Retrying an unchanged intention
recovers the stored input. Changed text or scope under the same identity
conflicts. Two writes commit different sequence numbers.

The first write selects an exact session, its binding and endpoint agent.
The ledger stores the original content and server-chosen expiry. The
receipt contains metadata only. The write transaction allocates sequence
and records that receipt together. Before a caller acknowledges input it
must commit the unit of work. Acceptance creates no R4 operation, outbox
record or lease. A full queue refuses a new input and preserves retries of
prior inputs. SQL constraints maintain one canonical operation link and
keep possible effect on an unknown transmission.

Five SQLite tests used the full migration set and isolated fixture rows.
They covered rollback and retry across transactions, session and generation
isolation, two simultaneous authors, bounded pending intake and the writer
and workspace-binding guards. The scope
rows represent metadata only. The tests deliberately create no valid
lease or grant and do not confer operator authority. The final combined
session interaction and NS-00 run passed 32 cases.

The storage function is internal and no HTTP or CLI surface calls it yet.
The route must prove a current human authority reference. The processor
must reserve at the existing R4 capacity gate and revalidate authority
before an effect. TTL enforcement, pause/resume and cancellation are
worker and control behavior in subsequent stages. The migration's next
use must preserve uncertain operation links and accepted rows on rollback.
No migration was applied to the global installation.
