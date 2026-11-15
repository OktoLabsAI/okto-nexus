# Connector reconciliation retirement checkpoint

Source and isolated installed-wheel qualification complete; documentation publication awaits final root review. No current service, database, credential or campaign package is changed by this curation.

The offline reproduction identifies a concrete missing-outbox path: accepted reconciliation could lack a durable retirement checkpoint when no prior direct session.release row existed. Schema6 adds a separate typed accepted-reconciliation proof, preserving direct-release behavior and revalidating immutable scope/generations, fenced/STOPPED launch evidence and stream/watermark before idempotent retirement.

Source qualification:46 distinct fixed cases (22 new+24 regressions), plus4 separate diagnostic reproduction cases. Repeated runs are not counted twice. Initial24pass/21fixtureerrors, second21fixtureerrors,21pass and final2pass XML are retained; final2 overlaps one previous case. The errors were fixture protocol-ordering mistakes, corrected without bypassing product guards.

The currently draining Connector is not fixed or released by offline evidence. Its latest root observation remains UNKNOWN/live; this diagnosis does not prove the sole live blocker, physical exit or safe force. No scenario/AC promotion, budget change, DB migration or implicit authorization follows.

Operational schema boundary: migration5→6 is tested offline. An older reader rejects user_version6, so an in-place binary downgrade is not claimed compatible. No live database migration has occurred. Source commit a8bd48bd is separate from the installed campaign package.

Installed qualification:24 PASS/4.734s, all overlapping source46, with988 wheel payloads verified under the new isolated prefix. Connector wheel2b8ce688541a5ae6e9806467569be0743fef6ff607c763f2b93accf0f93e017d comes from sourcea8bd48bd. This is not deployment into the active campaign.
