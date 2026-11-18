# SI-010 promote a queued input to an exact turn

The internal coordinator promotes a queued input owned by the same login
and surface. It checks the queue and input revisions, the original grant,
the exact turn, and both current capability and confirmed effect revisions.
An unresolved next-turn capacity attempt for that input blocks promotion.
The writer links the existing input to the derived canonical R4 steer
operation and commits its confirmation alongside the operation. A repeated
matching request reads the retained receipt. The text and ID stay with
that receipt.

The existing R4 control lane checks the original authority and the exact
effect again at the send cut. A paused queue, stale capability or revoked
login refuses the promoted control before sending. A promoted operation
uses the R4 control lane. It never consumes a next-turn capacity reservation.
The send cut marks possible effect on the linked input, which uses the
existing receipt and reconciliation projection after dispatch.

The R4 and queue regression passed 55 cases. The exact promotion fixture and
the migration suite passed 8 cases after adding the pause guard. The fixture
checks reservation precedence in both directions, stable receipt recovery,
effect mismatches, target changes, pause, revoked authority and the exact
R4 frame. It uses synthetic revisions and target facts.

The caller still needs authoritative adapter effect facts, including Pi's
boundary and Claude's compound behavior where qualified. Direct steer of
new text, presentation of the confirmed effect, and the live adapter matrix
remain pending. Migration 176 adds nullable effect confirmation to the
existing control provenance. Rollback after migration requires a build
that understands schema 176 and preserves its linked operations.
